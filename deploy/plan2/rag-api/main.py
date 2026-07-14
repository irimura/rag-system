"""案2 RAG API: LangChain の RAG チェーンを OpenAI 互換 API として公開する。

Open WebUI からは 1 つのモデル(RAG_MODEL_NAME)に見える。
検索(Qdrant)→ リランク(TEI /rerank)→ 生成(Node A の vLLM)。
"""
import json
import os
import time
import uuid

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from langchain_openai import ChatOpenAI
from langchain_qdrant import QdrantVectorStore
from pydantic import BaseModel

VLLM_BASE_URL = os.environ["VLLM_BASE_URL"]
VLLM_MODEL = os.environ["VLLM_MODEL"]
RAG_MODEL_NAME = os.getenv("RAG_MODEL_NAME", "knowledge-rag")
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "knowledge")
TEI_EMBED_URL = os.getenv("TEI_EMBED_URL", "http://tei-embed:80")
TEI_RERANK_URL = os.getenv("TEI_RERANK_URL", "http://tei-rerank:80")
RETRIEVE_K = int(os.getenv("RETRIEVE_K", "20"))
RERANK_TOP_N = int(os.getenv("RERANK_TOP_N", "4"))
RERANK_THRESHOLD = float(os.getenv("RERANK_THRESHOLD", "0.1"))

PROMPT = """以下のコンテキストのみに基づいて日本語で回答してください。
コンテキストに答えが含まれない場合は、推測せず「資料からは回答できません」と答えてください。

# コンテキスト
{context}

# 質問
{question}"""

NO_ANSWER = "資料からは回答できません。関連する文書が見つかりませんでした。"

llm = ChatOpenAI(
    base_url=VLLM_BASE_URL,
    api_key=os.getenv("VLLM_API_KEY", "dummy"),
    model=VLLM_MODEL,
    temperature=0,
)
embeddings = HuggingFaceEndpointEmbeddings(model=TEI_EMBED_URL)

app = FastAPI(title="rag-api")
_retriever = None


def get_retriever():
    """コレクションは ingest 実行後に存在するため遅延初期化する。"""
    global _retriever
    if _retriever is None:
        try:
            vs = QdrantVectorStore.from_existing_collection(
                embedding=embeddings, url=QDRANT_URL, collection_name=QDRANT_COLLECTION)
        except Exception as e:
            raise HTTPException(
                status_code=503,
                detail=f"Qdrant コレクション '{QDRANT_COLLECTION}' がありません。先に ingest を実行してください: {e}")
        _retriever = vs.as_retriever(
            search_type="mmr", search_kwargs={"k": RETRIEVE_K, "fetch_k": RETRIEVE_K * 3})
    return _retriever


async def rerank(question: str, docs: list) -> list:
    """TEI の /rerank でスコアリングし、しきい値以上の上位 top_n 件に絞る。"""
    if not docs:
        return []
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(f"{TEI_RERANK_URL}/rerank", json={
            "query": question, "texts": [d.page_content for d in docs]})
        res.raise_for_status()
    ranked = sorted(res.json(), key=lambda x: x["score"], reverse=True)
    return [docs[r["index"]] for r in ranked[:RERANK_TOP_N] if r["score"] >= RERANK_THRESHOLD]


async def retrieve_docs(question: str) -> tuple[list, list]:
    """本番応答と評価で共有する MMR 検索 + rerank 経路。"""
    candidates = await get_retriever().ainvoke(question)
    return candidates, await rerank(question, candidates)


def serialize_doc(doc) -> dict:
    """評価用エンドポイントへ必要最小限の Document 情報を返す。"""
    return {"page_content": doc.page_content, "metadata": doc.metadata}


def sources_footer(docs: list) -> str:
    sources = sorted({os.path.basename(d.metadata.get("source", "不明")) for d in docs})
    return "\n\n---\n参考資料: " + " / ".join(sources) if sources else ""


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str | None = None
    messages: list[ChatMessage]
    stream: bool = False


class RetrievalRequest(BaseModel):
    question: str


def completion_chunk(chunk_id: str, created: int, content: str | None, finish: str | None = None) -> str:
    delta = {"content": content} if content is not None else {}
    body = {"id": chunk_id, "object": "chat.completion.chunk", "created": created,
            "model": RAG_MODEL_NAME,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    return f"data: {json.dumps(body, ensure_ascii=False)}\n\n"


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/internal/evaluation/retrieve")
async def evaluation_retrieve(req: RetrievalRequest):
    """評価専用。認可は設けず、ホスト公開だけ Compose で 127.0.0.1 に限定する。"""
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question が空です")
    candidates, docs = await retrieve_docs(req.question)
    return {
        "candidates": [serialize_doc(doc) for doc in candidates],
        "reranked": [serialize_doc(doc) for doc in docs],
        "settings": {
            "retrieve_k": RETRIEVE_K,
            "rerank_top_n": RERANK_TOP_N,
            "rerank_threshold": RERANK_THRESHOLD,
        },
    }


@app.get("/v1/models")
async def models():
    return {"object": "list",
            "data": [{"id": RAG_MODEL_NAME, "object": "model", "created": 0, "owned_by": "rag-api"}]}


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    question = next((m.content for m in reversed(req.messages) if m.role == "user"), "")
    if not question:
        raise HTTPException(status_code=400, detail="user メッセージがありません")

    _, docs = await retrieve_docs(question)
    chunk_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())

    if not docs:
        answer = NO_ANSWER
        if not req.stream:
            return _completion_response(chunk_id, created, answer)

        async def no_answer_stream():
            yield completion_chunk(chunk_id, created, answer)
            yield completion_chunk(chunk_id, created, None, finish="stop")
            yield "data: [DONE]\n\n"
        return StreamingResponse(no_answer_stream(), media_type="text/event-stream")

    context = "\n\n".join(f"[{i + 1}] {d.page_content}" for i, d in enumerate(docs))
    prompt = PROMPT.format(context=context, question=question)
    footer = sources_footer(docs)

    if not req.stream:
        res = await llm.ainvoke(prompt)
        return _completion_response(chunk_id, created, res.content + footer)

    async def token_stream():
        async for part in llm.astream(prompt):
            if part.content:
                yield completion_chunk(chunk_id, created, part.content)
        yield completion_chunk(chunk_id, created, footer)
        yield completion_chunk(chunk_id, created, None, finish="stop")
        yield "data: [DONE]\n\n"
    return StreamingResponse(token_stream(), media_type="text/event-stream")


def _completion_response(chunk_id: str, created: int, content: str) -> dict:
    return {"id": chunk_id, "object": "chat.completion", "created": created,
            "model": RAG_MODEL_NAME,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}
