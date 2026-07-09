"""取り込みバッチ: documents/ 配下の文書を OpenSearch に登録する。

BM25(kuromoji + bi-gram)とベクトル(knn_vector)を同じインデックスに持つ。
インデックス定義: opensearch/index-mapping.json

実行: docker compose --profile ingest run --rm ingest
全再構築: FORCE_RECREATE=1 docker compose --profile ingest run --rm ingest
"""
import json
import os

from langchain_huggingface import HuggingFaceEndpointEmbeddings
from opensearchpy import OpenSearch, helpers

from common import load_documents, split_documents

OPENSEARCH_URL = os.getenv("OPENSEARCH_URL", "http://opensearch:9200")
INDEX = os.getenv("OS_INDEX", "knowledge")
EMBED_DIM = int(os.getenv("EMBED_DIM", "1024"))
BATCH = 32


def ensure_index(client: OpenSearch):
    if os.getenv("FORCE_RECREATE", "0") == "1" and client.indices.exists(INDEX):
        client.indices.delete(INDEX)
        print(f"インデックス {INDEX} を削除しました")
    if not client.indices.exists(INDEX):
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

    client = OpenSearch(OPENSEARCH_URL)
    ensure_index(client)
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
