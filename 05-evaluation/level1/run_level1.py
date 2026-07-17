#!/usr/bin/env python3
"""レベル1: Retrieval 評価スクリプト(案2: Qdrant + TEI 構成向けサンプル)。

Node B 上で実行し、127.0.0.1 に公開済みの rag-api 評価用エンドポイントを叩く。
rag-api 本番応答と同じ MMR 検索・TEI rerank の結果から
Hit Rate@K / Evidence Recall@K / MRR / nDCG を算出する。

使い方:
    python run_level1.py                       # 全件評価
    python run_level1.py --case TC01-001 -v    # 単一ケースの詳細表示
"""
import argparse
import json
import math
import os
from collections import defaultdict

RAG_API_URL = os.getenv("RAG_API_URL", "http://localhost:8000")
GOLDEN_PATH = os.getenv("GOLDEN_PATH", "../golden_dataset.sample.jsonl")

def load_cases(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def retrieve(question: str, groups: list[str] | None = None) -> dict:
    """rag-api 本番応答と共有された検索経路の候補・rerank 結果を取得する。"""
    import httpx

    token = os.getenv("RAG_EVAL_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    payload = {"question": question}
    if groups:
        payload["groups"] = groups
    with httpx.Client(timeout=60) as client:
        res = client.post(
            f"{RAG_API_URL}/internal/evaluation/retrieve",
            json=payload, headers=headers)
        res.raise_for_status()
        return res.json()


def matching_evidence(case: dict, chunk: dict) -> set[int]:
    """本文に quote が含まれる正解根拠の添字を返す。doc_id だけでは加点しない。"""
    text = chunk.get("page_content", "")
    matches = set()
    for index, evidence in enumerate(case.get("evidence", [])):
        if evidence.get("quote") and evidence["quote"] in text:
            matches.add(index)
    return matches


def score_ranking(case: dict, chunks: list[dict], k: int) -> dict:
    """同一 evidence の重複取得を二重加点せず、順位指標と網羅率を計算する。"""
    evidence_count = len(case.get("evidence", []))
    covered = set()
    gain_flags = []
    for chunk in chunks[:k]:
        new_matches = matching_evidence(case, chunk) - covered
        gain_flags.append(bool(new_matches))
        covered.update(new_matches)

    first_rank = next((i + 1 for i, hit in enumerate(gain_flags) if hit), None)
    dcg = sum(1.0 / math.log2(i + 2) for i, hit in enumerate(gain_flags) if hit)
    ideal_hits = min(evidence_count, k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))
    return {
        "hit": bool(covered),
        "evidence_recall": len(covered) / evidence_count if evidence_count else 0.0,
        "rr": 1.0 / first_rank if first_rank else 0.0,
        "ndcg": dcg / idcg if idcg else 0.0,
    }


def score_case(
        case: dict, candidates: list[dict], reranked: list[dict],
        retrieve_k: int, final_k: int) -> dict:
    pre = score_ranking(case, candidates, retrieve_k)
    post = score_ranking(case, reranked, final_k)
    return {
        "hit_pre": pre["hit"],
        "hit_post": post["hit"],
        "evidence_recall_pre": pre["evidence_recall"],
        "evidence_recall_post": post["evidence_recall"],
        "rr": post["rr"],
        "ndcg": post["ndcg"],
        "candidates": candidates,
        "reranked": reranked,
        "retrieve_k": retrieve_k,
        "final_k": final_k,
    }


def evaluate_case(case: dict, groups: list[str] | None = None) -> dict:
    result = retrieve(case["question"], groups)
    settings = result["settings"]
    return score_case(
        case, result["candidates"], result["reranked"],
        settings["retrieve_k"], settings["rerank_top_n"])


def show_verbose(case: dict, result: dict) -> None:
    print(f"\n[{case['id']}] {case['question']}")
    print(f"  evidence: {case.get('evidence')}")
    for i, c in enumerate(result["reranked"], 1):
        matches = matching_evidence(case, c)
        mark = f"E{','.join(str(i + 1) for i in sorted(matches))}" if matches else "-"
        src = (c.get("metadata") or {}).get("source", "?")
        print(f"  {mark:5s} #{i} [{src}] {c.get('page_content', '')[:80]}...")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", help="単一ケース ID のみ評価(例: TC01-001)")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--groups", nargs="+", help="評価対象グループ(例: --groups dept-a dept-b)")
    args = parser.parse_args()

    cases = [c for c in load_cases(GOLDEN_PATH) if c.get("answerable", True)]
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
        if not cases:
            raise SystemExit(f"ケース {args.case} が見つかりません(answerable=false は対象外)")

    results, by_cat = [], defaultdict(list)
    for case in cases:
        r = evaluate_case(case, args.groups)
        results.append(r)
        by_cat[case["category"]].append(r)
        if args.verbose:
            show_verbose(case, r)

    n = len(results)
    retrieve_k = results[0]["retrieve_k"]
    final_k = results[0]["final_k"]
    hr_pre = sum(r["hit_pre"] for r in results) / n
    hr_post = sum(r["hit_post"] for r in results) / n
    recall_pre = sum(r["evidence_recall_pre"] for r in results) / n
    recall_post = sum(r["evidence_recall_post"] for r in results) / n
    mrr = sum(r["rr"] for r in results) / n
    ndcg = sum(r["ndcg"] for r in results) / n

    print("\n=== レベル1: Retrieval 評価 ===")
    print(f"対象: {n} ケース(answerable のみ。TC07 は対象外)")
    print(f"HitRate@{retrieve_k} (Rerank 前): {hr_pre:.3f}")
    print(f"HitRate@{final_k}  (Rerank 後): {hr_post:.3f}")
    print(f"EvidenceRecall@{retrieve_k} (Rerank 前): {recall_pre:.3f}")
    print(f"EvidenceRecall@{final_k}  (Rerank 後): {recall_post:.3f}")
    print(f"MRR@{final_k}                 : {mrr:.3f}")
    print(f"nDCG@{final_k}                : {ndcg:.3f}")
    print(f"--- カテゴリ別 HitRate@{final_k} ---")
    for cat in sorted(by_cat):
        rs = by_cat[cat]
        hits = sum(r["hit_post"] for r in rs)
        print(f"{cat:24s}: {hits / len(rs):.3f} ({hits}/{len(rs)})")

    print("\n実験管理表用(05-evaluation/experiments.md に追記):")
    print(f"| | | | {hr_post:.2f} | {recall_post:.2f} | {mrr:.2f} | - | - | - | HR@{retrieve_k}前={hr_pre:.2f} |")


if __name__ == "__main__":
    main()
