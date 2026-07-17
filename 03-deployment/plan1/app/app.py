"""案1: Chainlit WebUI + LangChain RAG(単一プロセス)。"""
import os

import chainlit as cl
from langchain.retrievers import ContextualCompressionRetriever
from langchain.retrievers.document_compressors import CrossEncoderReranker
from langchain_chroma import Chroma
from langchain_community.cross_encoders import HuggingFaceCrossEncoder
from langchain_openai import ChatOpenAI

from common import build_embeddings

llm = ChatOpenAI(
    base_url=os.environ["VLLM_BASE_URL"],  # Node A(GPU ノード)の vLLM
    api_key=os.getenv("VLLM_API_KEY", "dummy"),
    model=os.environ["VLLM_MODEL"],
    temperature=0,
)

vectorstore = Chroma(
    persist_directory=os.getenv("CHROMA_DIR", "/data/chroma_db"),
    embedding_function=build_embeddings(),
)

reranker = CrossEncoderReranker(
    model=HuggingFaceCrossEncoder(model_name=os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")),
    top_n=int(os.getenv("RERANK_TOP_N", "4")),
)
retriever = ContextualCompressionRetriever(
    base_compressor=reranker,
    base_retriever=vectorstore.as_retriever(
        search_kwargs={"k": int(os.getenv("RETRIEVE_K", "20"))}),
)

PROMPT = """以下のコンテキストのみに基づいて日本語で回答してください。
コンテキストに答えが含まれない場合は、推測せず「資料からは回答できません」と答えてください。

# コンテキスト
{context}

# 質問
{question}"""


@cl.on_message
async def on_message(message: cl.Message):
    docs = await retriever.ainvoke(message.content)
    if not docs:
        await cl.Message(content="資料からは回答できません。").send()
        return

    context = "\n\n".join(f"[{i + 1}] {d.page_content}" for i, d in enumerate(docs))
    res = await llm.ainvoke(PROMPT.format(context=context, question=message.content))

    sources = sorted({os.path.basename(d.metadata.get("source", "不明")) for d in docs})
    footer = "\n\n---\n参考資料: " + " / ".join(sources)
    await cl.Message(content=res.content + footer).send()
