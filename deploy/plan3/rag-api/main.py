"""案3 RAG API: rag-api filter と OpenSearch DLS の二層でグループ認可する。"""
import json
import os
import time
import uuid
from typing import TypedDict

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from auth import Principal, derive_group_password, require_principal
from opensearch_client import build_opensearch_client
from query_rewrite import build_rewrite_prompt

VLLM_BASE_URL = os.environ["VLLM_BASE_URL"]
VLLM_MODEL = os.environ["VLLM_MODEL"]
RAG_MODEL_NAME = os.getenv("RAG_MODEL_NAME", "knowledge-rag")
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
NO_ANSWER = "資料からは回答できません。関連する文書が見つかりませんでした。"

llm = ChatOpenAI(base_url=VLLM_BASE_URL, api_key=os.getenv("VLLM_API_KEY", "dummy"),
                 model=VLLM_MODEL, temperature=0)
embeddings = HuggingFaceEndpointEmbeddings(model=TEI_EMBED_URL)
health_client = build_opensearch_client()
_group_clients = {}


def client_for_group(group: str):
    """DLS が設定されたグループ別 internal user のクライアントを返す。"""
    if group not in _group_clients:
        _group_clients[group] = build_opensearch_client(
            username=f"rag_{group}",
            password=derive_group_password(group),
        )
    return _group_clients[group]


def bm25_search(query: str, groups: list[str], client) -> list[dict]:
    body = {"size": SEARCH_K, "query": {"bool": {
        "must": [{"multi_match": {
            "query": query,
            "fields": ["text", "text.bigram"],
            "type": "most_fields",
        }}],
        "filter": [{"terms": {"group": groups}}],
    }}}
    return client.search(index=INDEX, body=body)["hits"]["hits"]


def knn_search(vector: list[float], groups: list[str], client) -> list[dict]:
    body = {"size": SEARCH_K, "query": {"bool": {
        "must": [{"knn": {"vector": {"vector": vector, "k": SEARCH_K}}}],
        "filter": [{"terms": {"group": groups}}],
    }}}
    return client.search(index=INDEX, body=body)["hits"]["hits"]


def rrf_fuse(result_lists: list[list[dict]]) -> list[dict]:
    fused: dict[str, dict] = {}
    for results in result_lists:
        for rank, hit in enumerate(results):
            entry = fused.setdefault(hit["_id"], {"hit": hit, "score": 0.0})
            entry["score"] += 1.0 / (RRF_K + rank + 1)
    ranked = sorted(fused.values(), key=lambda item: item["score"], reverse=True)
    return [entry["hit"] for entry in ranked[:RETRIEVE_K]]


async def rerank(query: str, hits: list[dict]) -> list[dict]:
    if not hits:
        return []
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(f"{TEI_RERANK_URL}/rerank", json={
            "query": query, "texts": [hit["_source"]["text"] for hit in hits]})
        res.raise_for_status()
    ranked = sorted(res.json(), key=lambda item: item["score"], reverse=True)
    return [hits[item["index"]] for item in ranked[:RERANK_TOP_N]
            if item["score"] >= RERANK_THRESHOLD]


class RagState(TypedDict):
    question: str
    query: str
    docs: list[dict]
    answer: str
    attempts: int
    previous_queries: list[str]
    groups: list[str]


async def node_rewrite(state: RagState) -> dict:
    if state["attempts"] == 0:
        return {"query": state["question"]}
    res = await llm.ainvoke(build_rewrite_prompt(
        question=state["question"],
        previous_queries=state["previous_queries"],
        attempt=state["attempts"],
    ))
    return {"query": res.content.strip()}


async def node_retrieve(state: RagState) -> dict:
    vector = await embeddings.aembed_query(state["query"])
    result_lists = []
    for group in state["groups"]:
        client = client_for_group(group)
        result_lists.append(bm25_search(state["query"], state["groups"], client))
        result_lists.append(knn_search(vector, state["groups"], client))
    fused = rrf_fuse(result_lists)
    docs = await rerank(state["question"], fused)
    return {
        "docs": docs,
        "attempts": state["attempts"] + 1,
        "previous_queries": [*state["previous_queries"], state["query"]],
    }


def route_grade(state: RagState) -> str:
    if state["docs"]:
        return "generate"
    if state["attempts"] <= MAX_RETRIES:
        return "rewrite"
    return "no_answer"


async def node_generate(state: RagState) -> dict:
    context = "\n\n".join(
        f"[{index + 1}] {hit['_source']['text']}" for index, hit in enumerate(state["docs"]))
    res = await llm.ainvoke(PROMPT.format(context=context, question=state["question"]))
    return {"answer": res.content}


def node_no_answer(state: RagState) -> dict:
    return {"answer": NO_ANSWER}


def build_graph():
    graph_builder = StateGraph(RagState)
    graph_builder.add_node("rewrite", node_rewrite)
    graph_builder.add_node("retrieve", node_retrieve)
    graph_builder.add_node("generate", node_generate)
    graph_builder.add_node("no_answer", node_no_answer)
    graph_builder.set_entry_point("rewrite")
    graph_builder.add_edge("rewrite", "retrieve")
    graph_builder.add_conditional_edges(
        "retrieve", route_grade,
        {"generate": "generate", "rewrite": "rewrite", "no_answer": "no_answer"})
    graph_builder.add_edge("generate", END)
    graph_builder.add_edge("no_answer", END)
    return graph_builder.compile()


graph = build_graph()
app = FastAPI(title="rag-api")


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str | None = None
    messages: list[ChatMessage]
    stream: bool = False


def sources_footer(docs: list[dict]) -> str:
    sources = sorted({hit["_source"].get("source", "不明") for hit in docs})
    return "\n\n---\n参考資料: " + " / ".join(sources) if sources else ""


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/v1/models")
async def list_models():
    return {"object": "list",
            "data": [{"id": RAG_MODEL_NAME, "object": "model", "created": 0,
                      "owned_by": "rag-api"}]}


@app.post("/v1/chat/completions")
async def chat_completions(
    req: ChatRequest,
    principal: Principal = Depends(require_principal),
):
    question = next((message.content for message in reversed(req.messages)
                     if message.role == "user"), "")
    if not question:
        raise HTTPException(status_code=400, detail="user メッセージがありません")
    if not health_client.indices.exists(INDEX):
        raise HTTPException(status_code=503,
                            detail=f"インデックス '{INDEX}' がありません。先に ingest を実行してください。")

    result = await graph.ainvoke(
        {"question": question, "query": "", "docs": [], "answer": "",
         "attempts": 0, "previous_queries": [], "groups": principal.groups})
    content = result["answer"] + (sources_footer(result["docs"]) if result["docs"] else "")
    response_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())

    if not req.stream:
        return {"id": response_id, "object": "chat.completion", "created": created,
                "model": RAG_MODEL_NAME,
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

    async def pseudo_stream():
        body = {"id": response_id, "object": "chat.completion.chunk", "created": created,
                "model": RAG_MODEL_NAME,
                "choices": [{"index": 0, "delta": {"content": content},
                             "finish_reason": None}]}
        yield f"data: {json.dumps(body, ensure_ascii=False)}\n\n"
        body["choices"] = [{"index": 0, "delta": {}, "finish_reason": "stop"}]
        yield f"data: {json.dumps(body, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(pseudo_stream(), media_type="text/event-stream")
