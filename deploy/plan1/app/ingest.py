"""取り込みバッチ: documents/ 配下の PDF/MD/TXT を Chroma に登録する。

実行: docker compose --profile ingest run --rm ingest
既存コレクションは毎回削除し、documents/ 全体から再構築する。
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

    embeddings = build_embeddings()
    existing = Chroma(persist_directory=chroma_dir, embedding_function=embeddings)
    existing.delete_collection()
    print("既存の Chroma コレクションを削除しました")

    Chroma.from_documents(chunks, embeddings, persist_directory=chroma_dir)
    print(f"Chroma へ登録完了: {chroma_dir}")


if __name__ == "__main__":
    main()
