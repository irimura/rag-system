#!/usr/bin/env python3
"""レベル1: Retrieval 評価スクリプト(案2: Qdrant + TEI 構成向けサンプル)。

Node B 上で実行し、127.0.0.1 に公開済みのデバッグポートを直接叩く。
rag-api と同じ「TEI embed -> Qdrant 検索 -> TEI rerank」を再現して
Hit Rate@K / MRR / nDCG を算出する。

使い方:
    python run_level1.py                       # 全件評価
    python run_level1.py --case TC01-001 -v    # 単一ケースの詳細表示
"""
import argparse
import json
import math
import os
from collections import defaultdict

import httpx

TEI_EMBED_URL = os.getenv("TEI_EMBED_URL", "http://localhost:8081")
TEI_RERANK_URL = os.getenv("TEI_RERANK_URL", "http://localhost:8082")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION = os.getenv("QDRANT_COLLECTION", "knowledge")
GOLDEN_PATH = os.getenv("GOLDEN_PATH", "../../eval/golden_dataset.sample.jsonl")
RETRIEVE_K = int(os.getenv("RETRIEVE_K", "20"))   # Rerank 前の候補数
FINAL_K = int(os.getenv("FINAL_K", "5"))          # Rerank 後の評価対象件数

client = httpx.Client(timeout=60)


def load_cases(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def embed(text: str) -> list[float]:
    res = client.post(f"{TEI_EMBED_URL}/embed", json={"inputs": [text]})
    res.raise_for_status()
    return res.json()[0]


def search(vector: list[float], k: int) -> list[dict]:
    """Qdrant 検索。langchain-qdrant の payload 形式(page_content / metadata)を返す。"""
    res = client.post(
        f"{QDRANT_URL}/collections/{COLLECTION}/points/search",
        json={"vector": vector, "limit": k, "with_payload": True})
    res.raise_for_status()
    return [p["payload"] for p in res.json()["result"]]


def rerank(question: str, chunks: list[dict], top_n: int) -> list[dict]:
    res = client.post(f"{TEI_RERANK_URL}/rerank", json={
        "query": question, "texts": [c.get("page_content", "") for c in chunks]})
    res.raise_for_status()
    ranked = sorted(res.json(), key=lambda x: x["score"], reverse=True)
    return [chunks[r["index"]] for r in ranked[:top_n]]


def is_hit(case: dict, chunk: dict) -> bool:
    """quote の部分一致、または doc_id と source の一致で正解根拠と判定する。"""
    text = chunk.get("page_content", "")
    source = str((chunk.get("metadata") or {}).get("source", ""))
    for ev in case.get("evidence", []):
        if ev.get("quote") and ev["quote"] in text:
            return True
        if ev.get("doc_id") and ev["doc_id"] in source:
            return True
    return False


def evaluate_case(case: dict) -> dict:
    vector = embed(case["question"])
    candidates = search(vector, RETRIEVE_K)
    reranked = rerank(case["question"], candidates, FINAL_K)

    hit_pre = any(is_hit(case, c) for c in candidates)
    hit_flags = [is_hit(case, c) for c in reranked]
    first_rank = next((i + 1 for i, h in enumerate(hit_flags) if h), None)

    dcg = sum(1.0 / math.log2(i + 2) for i, h in enumerate(hit_flags) if h)
    ideal_hits = min(sum(hit_flags), FINAL_K) or 1
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))
    return {
        "hit_pre": hit_pre,
        "hit_post": first_rank is not None,
        "rr": 1.0 / first_rank if first_rank else 0.0,
        "ndcg": dcg / idcg if any(hit_flags) else 0.0,
        "candidates": candidates,
        "reranked": reranked,
    }


def show_verbose(case: dict, result: dict) -> None:
    print(f"\n[{case['id']}] {case['question']}")
    print(f"  evidence: {case.get('evidence')}")
    for i, c in enumerate(result["reranked"], 1):
        mark = "HIT " if is_hit(case, c) else "    "
        src = (c.get("metadata") or {}).get("source", "?")
        print(f"  {mark}#{i} [{src}] {c.get('page_content', '')[:80]}...")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", help="単一ケース ID のみ評価(例: TC01-001)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    cases = [c for c in load_cases(GOLDEN_PATH) if c.get("answerable", True)]
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
        if not cases:
            raise SystemExit(f"ケース {args.case} が見つかりません(answerable=false は対象外)")

    results, by_cat = [], defaultdict(list)
    for case in cases:
        r = evaluate_case(case)
        results.append(r)
        by_cat[case["category"]].append(r)
        if args.verbose:
            show_verbose(case, r)

    n = len(results)
    hr_pre = sum(r["hit_pre"] for r in results) / n
    hr_post = sum(r["hit_post"] for r in results) / n
    mrr = sum(r["rr"] for r in results) / n
    ndcg = sum(r["ndcg"] for r in results) / n

    print("\n=== レベル1: Retrieval 評価 ===")
    print(f"対象: {n} ケース(answerable のみ。TC07 は対象外)")
    print(f"HitRate@{RETRIEVE_K} (Rerank 前): {hr_pre:.3f}")
    print(f"HitRate@{FINAL_K}  (Rerank 後): {hr_post:.3f}")
    print(f"MRR@{FINAL_K}                 : {mrr:.3f}")
    print(f"nDCG@{FINAL_K}                : {ndcg:.3f}")
    print(f"--- カテゴリ別 HitRate@{FINAL_K} ---")
    for cat in sorted(by_cat):
        rs = by_cat[cat]
        hits = sum(r["hit_post"] for r in rs)
        print(f"{cat:24s}: {hits / len(rs):.3f} ({hits}/{len(rs)})")

    print("\n実験管理表用(eval/experiments.md に追記):")
    print(f"| | | | {hr_post:.2f} | {mrr:.2f} | - | - | - | HR@{RETRIEVE_K}前={hr_pre:.2f} |")


if __name__ == "__main__":
    main()
