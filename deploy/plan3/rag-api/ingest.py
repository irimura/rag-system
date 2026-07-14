"""取り込みバッチ: documents/ 配下の文書を OpenSearch に登録する。

BM25(kuromoji + bi-gram)とベクトル(knn_vector)を同じインデックスに持つ。
インデックス定義: opensearch/index-mapping.json

実行: docker compose --profile ingest run --rm ingest
既存インデックスは毎回削除し、documents/ 全体から再構築する。
"""
import json
import os

from langchain_huggingface import HuggingFaceEndpointEmbeddings
from opensearchpy import OpenSearch, helpers

from opensearch_client import build_opensearch_client

from common import load_documents, split_documents

INDEX = os.getenv("OS_INDEX", "knowledge")
EMBED_DIM = int(os.getenv("EMBED_DIM", "1024"))
BATCH = 32


def recreate_index(client: OpenSearch):
    if client.indices.exists(INDEX):
        client.indices.delete(INDEX)
        print(f"インデックス {INDEX} を削除しました")
    with open("index-mapping.json", encoding="utf-8") as f:
        body = json.load(f)
    body["mappings"]["properties"]["vector"]["dimension"] = EMBED_DIM
    client.indices.create(INDEX, body=body)
    print(f"インデックス {INDEX} を作成しました(dim={EMBED_DIM})")


def main():
    docs = load_documents(os.getenv("DOCS_DIR", "/data/documents"))
    if not docs:
        raise SystemExit("documents/ に文書がありません。PDF/MD/TXT を配置してください。")
    chunks = split_documents(docs)
    print(f"文書 {len(docs)} 件 -> チャンク {len(chunks)} 件")

    client = build_opensearch_client()
    recreate_index(client)
    embeddings = HuggingFaceEndpointEmbeddings(model=os.getenv("TEI_EMBED_URL", "http://tei-embed:80"))

    for i in range(0, len(chunks), BATCH):
        batch = chunks[i:i + BATCH]
        vectors = embeddings.embed_documents([c.page_content for c in batch])
        actions = [{
            "_index": INDEX,
            "_source": {
                "text": c.page_content,
                "vector": v,
                "source": os.path.basename(c.metadata.get("source", "不明")),
            },
        } for c, v in zip(batch, vectors)]
        helpers.bulk(client, actions)
        print(f"  {min(i + BATCH, len(chunks))}/{len(chunks)} 件登録")

    client.indices.refresh(INDEX)
    print(f"OpenSearch へ登録完了: {INDEX}")


if __name__ == "__main__":
    main()
