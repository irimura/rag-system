"""取り込みバッチ: documents/ 配下の PDF/MD/TXT を Qdrant に登録する。

実行: docker compose --profile ingest run --rm ingest
全再構築: FORCE_RECREATE=1 docker compose --profile ingest run --rm ingest
"""
import os

from langchain_huggingface import HuggingFaceEndpointEmbeddings
from langchain_qdrant import QdrantVectorStore

from common import load_documents, split_documents


def main():
    docs = load_documents(os.getenv("DOCS_DIR", "/data/documents"))
    if not docs:
        raise SystemExit("documents/ に文書がありません。PDF/MD/TXT を配置してください。")
    chunks = split_documents(docs)
    print(f"文書 {len(docs)} 件 -> チャンク {len(chunks)} 件")

    embeddings = HuggingFaceEndpointEmbeddings(model=os.getenv("TEI_EMBED_URL", "http://tei-embed:80"))
    QdrantVectorStore.from_documents(
        chunks,
        embeddings,
        url=os.getenv("QDRANT_URL", "http://qdrant:6333"),
        collection_name=os.getenv("QDRANT_COLLECTION", "knowledge"),
        force_recreate=os.getenv("FORCE_RECREATE", "0") == "1",
    )
    print("Qdrant へ登録完了")


if __name__ == "__main__":
    main()
