"""案2 RAG API: 認証済み principal のグループ内だけを Qdrant から検索する。"""
import json
import os
import time
import uuid

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from langchain_openai import ChatOpenAI
from langchain_qdrant import QdrantVectorStore
from pydantic import BaseModel
from qdrant_client import models

from auth import Principal, require_principal

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

llm = ChatOpenAI(base_url=VLLM_BASE_URL, api_key=os.getenv("VLLM_API_KEY", "dummy"),
                 model=VLLM_MODEL, temperature=0)
embeddings = HuggingFaceEndpointEmbeddings(model=TEI_EMBED_URL)
app = FastAPI(title="rag-api")
_vectorstore = None


def get_vectorstore():
    """コレクションは ingest 後に存在するため遅延初期化する。"""
    global _vectorstore
    if _vectorstore is None:
        try:
            _vectorstore = QdrantVectorStore.from_existing_collection(
                embedding=embeddings, url=QDRANT_URL, collection_name=QDRANT_COLLECTION)
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Qdrant コレクション '{QDRANT_COLLECTION}' がありません。先に ingest を実行してください: {exc}") from exc
    return _vectorstore


def get_retriever(groups: list[str]):
    group_filter = models.Filter(must=[
        models.FieldCondition(
            key="metadata.group",
            match=models.MatchAny(any=groups),
        )
    ])
    return get_vectorstore().as_retriever(
        search_type="mmr",
        search_kwargs={"k": RETRIEVE_K, "fetch_k": RETRIEVE_K * 3, "filter": group_filter},
    )


async def rerank(question: str, docs: list) -> list:
    if not docs:
        return []
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(f"{TEI_RERANK_URL}/rerank", json={
            "query": question, "texts": [doc.page_content for doc in docs]})
        res.raise_for_status()
    ranked = sorted(res.json(), key=lambda item: item["score"], reverse=True)
    return [docs[item["index"]] for item in ranked[:RERANK_TOP_N]
            if item["score"] >= RERANK_THRESHOLD]


async def retrieve_docs(question: str, groups: list[str]) -> tuple[list, list]:
    candidates = await get_retriever(groups).ainvoke(question)
    return candidates, await rerank(question, candidates)


def serialize_doc(doc) -> dict:
    return {"page_content": doc.page_content, "metadata": doc.metadata}


def sources_footer(docs: list) -> str:
    sources = sorted({os.path.basename(doc.metadata.get("source", "不明")) for doc in docs})
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
    groups: list[str] | None = None


def completion_chunk(chunk_id: str, created: int, content: str | None,
                     finish: str | None = None) -> str:
    delta = {"content": content} if content is not None else {}
    body = {"id": chunk_id, "object": "chat.completion.chunk", "created": created,
            "model": RAG_MODEL_NAME,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    return f"data: {json.dumps(body, ensure_ascii=False)}\n\n"


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/internal/evaluation/retrieve")
async def evaluation_retrieve(
    req: RetrievalRequest,
    principal: Principal = Depends(require_principal),
):
    """評価専用。EVAL_TOKEN または転送 JWT が必須。"""
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question が空です")
    groups = principal.groups
    if req.groups is not None:
        groups = sorted(set(principal.groups) & set(req.groups))
        if not groups:
            raise HTTPException(status_code=403, detail="要求グループへのアクセス権がありません")
    candidates, docs = await retrieve_docs(req.question, groups)
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

    _, docs = await retrieve_docs(question, principal.groups)
    chunk_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())

    if not docs:
        if not req.stream:
            return _completion_response(chunk_id, created, NO_ANSWER)

        async def no_answer_stream():
            yield completion_chunk(chunk_id, created, NO_ANSWER)
            yield completion_chunk(chunk_id, created, None, finish="stop")
            yield "data: [DONE]\n\n"
        return StreamingResponse(no_answer_stream(), media_type="text/event-stream")

    context = "\n\n".join(f"[{index + 1}] {doc.page_content}"
                            for index, doc in enumerate(docs))
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
