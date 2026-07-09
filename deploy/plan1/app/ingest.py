"""取り込みバッチ: documents/ 配下の PDF/MD/TXT を Chroma に登録する。

実行: docker compose --profile ingest run --rm ingest
"""
import os

from langchain_chroma import Chroma

from common import build_embeddings, load_documents, split_documents


def main():
    docs_dir = os.getenv("DOCS_DIR", "/data/documents")
    chroma_dir = os.getenv("CHROMA_DIR", "/data/chroma_db")

    docs = load_documents(docs_dir)
    if not docs:
        raise SystemExit(f"{docs_dir} に文書がありません。PDF/MD/TXT を配置してください。")
    chunks = split_documents(docs)
    print(f"文書 {len(docs)} 件 -> チャンク {len(chunks)} 件")

    Chroma.from_documents(chunks, build_embeddings(), persist_directory=chroma_dir)
    print(f"Chroma へ登録完了: {chroma_dir}")


if __name__ == "__main__":
    main()
