"""案3 RAG API: LangGraph によるハイブリッド検索フローを OpenAI 互換 API として公開する。

フロー: クエリ書き換え -> ハイブリッド検索(BM25 + kNN を RRF 統合)-> リランク
        -> 関連度チェック(不十分なら別観点で再検索、上限まで)-> 生成 or 「該当なし」
"""
import json
import os
import time
import uuid
from typing import TypedDict

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from opensearchpy import OpenSearch
from pydantic import BaseModel

VLLM_BASE_URL = os.environ["VLLM_BASE_URL"]
VLLM_MODEL = os.environ["VLLM_MODEL"]
RAG_MODEL_NAME = os.getenv("RAG_MODEL_NAME", "knowledge-rag")
OPENSEARCH_URL = os.getenv("OPENSEARCH_URL", "http://opensearch:9200")
INDEX = os.getenv("OS_INDEX", "knowledge")
TEI_EMBED_URL = os.getenv("TEI_EMBED_URL", "http://tei-embed:80")
TEI_RERANK_URL = os.getenv("TEI_RERANK_URL", "http://tei-rerank:80")
SEARCH_K = int(os.getenv("SEARCH_K", "30"))
RETRIEVE_K = int(os.getenv("RETRIEVE_K", "20"))
RERANK_TOP_N = int(os.getenv("RERANK_TOP_N", "5"))
RERANK_THRESHOLD = float(os.getenv("RERANK_THRESHOLD", "0.1"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "2"))
RRF_K = 60

PROMPT = """以下のコンテキストのみに基づいて日本語で回答してください。
コンテキストに答えが含まれない場合は、推測せず「資料からは回答できません」と答えてください。

# コンテキスト
{context}

# 質問
{question}"""

REWRITE_PROMPT = """次の質問で文書検索をしましたが、関連する文書が見つかりませんでした。
同じ内容を別の言葉(同義語・正式名称・漢語/和語の言い換え)で表した検索クエリを 1 つだけ出力してください。
説明は不要です。

質問: {question}"""

NO_ANSWER = "資料からは回答できません。関連する文書が見つかりませんでした。"

llm = ChatOpenAI(
    base_url=VLLM_BASE_URL,
    api_key=os.getenv("VLLM_API_KEY", "dummy"),
    model=VLLM_MODEL,
    temperature=0,
)
embeddings = HuggingFaceEndpointEmbeddings(model=TEI_EMBED_URL)
os_client = OpenSearch(OPENSEARCH_URL)


# --- ハイブリッド検索 ---

def bm25_search(query: str) -> list[dict]:
    body = {"size": SEARCH_K, "query": {"multi_match": {
        "query": query,
        "fields": ["text", "text.bigram"],   # 形態素解析 + bi-gram(未知語対策)
        "type": "most_fields"}}}
    return os_client.search(index=INDEX, body=body)["hits"]["hits"]


def knn_search(vector: list[float]) -> list[dict]:
    body = {"size": SEARCH_K, "query": {"knn": {"vector": {"vector": vector, "k": SEARCH_K}}}}
    return os_client.search(index=INDEX, body=body)["hits"]["hits"]


def rrf_fuse(result_lists: list[list[dict]]) -> list[dict]:
    """Reciprocal Rank Fusion: score = Σ 1 / (RRF_K + rank)"""
    fused: dict[str, dict] = {}
    for results in result_lists:
        for rank, hit in enumerate(results):
            entry = fused.setdefault(hit["_id"], {"hit": hit, "score": 0.0})
            entry["score"] += 1.0 / (RRF_K + rank + 1)
    ranked = sorted(fused.values(), key=lambda x: x["score"], reverse=True)
    return [e["hit"] for e in ranked[:RETRIEVE_K]]


async def rerank(query: str, hits: list[dict]) -> list[dict]:
    """TEI /rerank でスコアリングし、しきい値以上の上位 top_n 件に絞る。"""
    if not hits:
        return []
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(f"{TEI_RERANK_URL}/rerank", json={
            "query": query, "texts": [h["_source"]["text"] for h in hits]})
        res.raise_for_status()
    ranked = sorted(res.json(), key=lambda x: x["score"], reverse=True)
    return [hits[r["index"]] for r in ranked[:RERANK_TOP_N] if r["score"] >= RERANK_THRESHOLD]


# --- LangGraph 検索フロー ---

class RagState(TypedDict):
    question: str
    query: str
    docs: list[dict]
    answer: str
    attempts: int


async def node_rewrite(state: RagState) -> dict:
    if state["attempts"] == 0:
        return {"query": state["question"]}          # 初回は元の質問で検索
    res = await llm.ainvoke(REWRITE_PROMPT.format(question=state["question"]))
    return {"query": res.content.strip()}


async def node_retrieve(state: RagState) -> dict:
    vector = await embeddings.aembed_query(state["query"])
    fused = rrf_fuse([bm25_search(state["query"]), knn_search(vector)])
    docs = await rerank(state["question"], fused)
    return {"docs": docs, "attempts": state["attempts"] + 1}


def route_grade(state: RagState) -> str:
    if state["docs"]:
        return "generate"
    if state["attempts"] <= MAX_RETRIES:
        return "rewrite"                              # 別観点で再検索
    return "no_answer"


async def node_generate(state: RagState) -> dict:
    context = "\n\n".join(
        f"[{i + 1}] {h['_source']['text']}" for i, h in enumerate(state["docs"]))
    res = await llm.ainvoke(PROMPT.format(context=context, question=state["question"]))
    return {"answer": res.content}


def node_no_answer(state: RagState) -> dict:
    return {"answer": NO_ANSWER}


def build_graph():
    g = StateGraph(RagState)
    g.add_node("rewrite", node_rewrite)
    g.add_node("retrieve", node_retrieve)
    g.add_node("generate", node_generate)
    g.add_node("no_answer", node_no_answer)
    g.set_entry_point("rewrite")
    g.add_edge("rewrite", "retrieve")
    g.add_conditional_edges("retrieve", route_grade,
                            {"generate": "generate", "rewrite": "rewrite", "no_answer": "no_answer"})
    g.add_edge("generate", END)
    g.add_edge("no_answer", END)
    return g.compile()


graph = build_graph()


# --- OpenAI 互換 API ---

app = FastAPI(title="rag-api")


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str | None = None
    messages: list[ChatMessage]
    stream: bool = False


def sources_footer(docs: list[dict]) -> str:
    sources = sorted({h["_source"].get("source", "不明") for h in docs})
    return "\n\n---\n参考資料: " + " / ".join(sources) if sources else ""


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/v1/models")
async def models():
    return {"object": "list",
            "data": [{"id": RAG_MODEL_NAME, "object": "model", "created": 0, "owned_by": "rag-api"}]}


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    question = next((m.content for m in reversed(req.messages) if m.role == "user"), "")
    if not question:
        raise HTTPException(status_code=400, detail="user メッセージがありません")
    if not os_client.indices.exists(INDEX):
        raise HTTPException(status_code=503,
                            detail=f"インデックス '{INDEX}' がありません。先に ingest を実行してください。")

    result = await graph.ainvoke(
        {"question": question, "query": "", "docs": [], "answer": "", "attempts": 0})
    content = result["answer"] + (sources_footer(result["docs"]) if result["docs"] else "")

    resp_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())

    if not req.stream:
        return {"id": resp_id, "object": "chat.completion", "created": created,
                "model": RAG_MODEL_NAME,
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

    # LangGraph はグラフ完了後に回答が確定するため、確定済み回答を SSE で返す
    async def pseudo_stream():
        body = {"id": resp_id, "object": "chat.completion.chunk", "created": created,
                "model": RAG_MODEL_NAME,
                "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}]}
        yield f"data: {json.dumps(body, ensure_ascii=False)}\n\n"
        body["choices"] = [{"index": 0, "delta": {}, "finish_reason": "stop"}]
        yield f"data: {json.dumps(body, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(pseudo_stream(), media_type="text/event-stream")
