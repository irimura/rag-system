"""取り込みバッチ: documents/<group>/ 配下の文書を Qdrant に登録する。"""
import os
from collections import Counter

from langchain_huggingface import HuggingFaceEndpointEmbeddings
from langchain_qdrant import QdrantVectorStore

from common import assign_group_metadata, load_documents, split_documents


def main():
    docs_dir = os.getenv("DOCS_DIR", "/data/documents")
    docs = load_documents(docs_dir)
    if not docs:
        raise SystemExit("documents/ に文書がありません。PDF/MD/TXT を配置してください。")
    assign_group_metadata(docs, docs_dir)
    chunks = split_documents(docs)
    counts = Counter(chunk.metadata["group"] for chunk in chunks)
    print(f"文書 {len(docs)} 件 -> チャンク {len(chunks)} 件")
    print("グループ別チャンク数: " + ", ".join(f"{group}={counts[group]}" for group in sorted(counts)))

    embeddings = HuggingFaceEndpointEmbeddings(model=os.getenv("TEI_EMBED_URL", "http://tei-embed:80"))
    QdrantVectorStore.from_documents(
        chunks,
        embeddings,
        url=os.getenv("QDRANT_URL", "http://qdrant:6333"),
        collection_name=os.getenv("QDRANT_COLLECTION", "knowledge"),
        force_recreate=True,
    )
    print("Qdrant へ登録完了")


if __name__ == "__main__":
    main()
