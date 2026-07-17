#!/usr/bin/env python3
"""レベル2: Generation 評価スクリプト(案2 構成向けサンプル)。

rag-api の本番 OpenAI 互換 API で検索 + 生成を実行し、
1) TC07 の該当なし正答率(機械判定)
2) answerable ケースの Ragas 採点(judge = vLLM / embeddings = TEI)
を出力する。生成結果は answers.jsonl に保存される。

注意: 本スクリプトは requirements.txt で固定した ragas 0.2 系 API を使用する。
      0.4 系へ更新する場合は移行ガイドに従い evaluate と metrics API を同時に変更すること。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "level1"))
from run_level1 import RAG_API_URL, load_cases, retrieve  # noqa: E402

VLLM_BASE_URL = os.environ["VLLM_BASE_URL"]
VLLM_MODEL = os.environ["VLLM_MODEL"]
VLLM_API_KEY = os.getenv("VLLM_API_KEY", "dummy")
GOLDEN_PATH = os.getenv("GOLDEN_PATH", "../../eval/golden_dataset.sample.jsonl")
ANSWERS_PATH = os.getenv("ANSWERS_PATH", "answers.jsonl")
NO_ANSWER_PHRASE = "資料からは回答できません"


def generate_answer(question: str) -> str:
    """rag-api の本番 OpenAI 互換 API を呼び、検索・閾値・回答不能分岐・生成を共有する。"""
    import httpx

    token = os.getenv("RAG_EVAL_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with httpx.Client(timeout=180) as client:
        res = client.post(f"{RAG_API_URL}/v1/chat/completions", headers=headers, json={
            "model": "knowledge-rag",
            "messages": [{"role": "user", "content": question}],
            "stream": False,
        })
        res.raise_for_status()
        return res.json()["choices"][0]["message"]["content"]


def run_pipeline(cases: list[dict]) -> list[dict]:
    records = []
    for case in cases:
        # rag-api は最後の user メッセージだけを検索に使う。TC09 もその現状を評価する。
        question = case["question"]

        chunks = retrieve(question)["reranked"]
        contexts = [c.get("page_content", "") for c in chunks]
        answer = generate_answer(question)
        records.append({
            "id": case["id"], "category": case["category"],
            "user_input": case["question"], "retrieved_contexts": contexts,
            "response": answer, "reference": case["ground_truth"],
            "answerable": case.get("answerable", True),
        })
        print(f"  生成完了: {case['id']}")
    return records


def eval_abstention(records: list[dict]) -> None:
    targets = [r for r in records if not r["answerable"]]
    if not targets:
        print("該当なし正答率 (TC07)  : 対象ケースなし")
        return
    ok = sum(NO_ANSWER_PHRASE in r["response"] for r in targets)
    print(f"該当なし正答率 (TC07)  : {ok / len(targets):.3f} ({ok}/{len(targets)})")
    for r in targets:
        if NO_ANSWER_PHRASE not in r["response"]:
            print(f"  不合格(捏造の疑い): {r['id']} -> {r['response'][:80]}...")


def eval_ragas(records: list[dict]) -> None:
    from datasets import Dataset
    from langchain_huggingface import HuggingFaceEndpointEmbeddings
    from langchain_openai import ChatOpenAI
    from ragas import evaluate
    from ragas.metrics import answer_correctness, answer_relevancy, faithfulness

    targets = [r for r in records if r["answerable"]]
    dataset = Dataset.from_list([{
        "question": r["user_input"], "contexts": r["retrieved_contexts"],
        "answer": r["response"], "ground_truth": r["reference"],
    } for r in targets])

    judge = ChatOpenAI(base_url=VLLM_BASE_URL, api_key=VLLM_API_KEY,
                       model=VLLM_MODEL, temperature=0)
    embeddings = HuggingFaceEndpointEmbeddings(
        model=os.getenv("TEI_EMBED_URL", "http://localhost:8081"))
    result = evaluate(dataset,
                      metrics=[faithfulness, answer_relevancy, answer_correctness],
                      llm=judge, embeddings=embeddings)
    print(result)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate-only", action="store_true",
                        help="回答生成と TC07 判定のみ(Ragas をスキップ)")
    args = parser.parse_args()

    records = run_pipeline(load_cases(GOLDEN_PATH))
    with open(ANSWERS_PATH, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n生成結果を保存: {ANSWERS_PATH}")

    print("\n=== レベル2: Generation 評価 ===")
    eval_abstention(records)
    if not args.generate_only:
        eval_ragas(records)


if __name__ == "__main__":
    main()
