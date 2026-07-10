#!/usr/bin/env python3
"""レベル2: Generation 評価スクリプト(案2 構成向けサンプル)。

検索(レベル1 と同一ロジック)+ 生成(vLLM、rag-api と同一プロンプト)を実行し、
1) TC07 の該当なし正答率(機械判定)
2) answerable ケースの Ragas 採点(judge = vLLM / embeddings = TEI)
を出力する。生成結果は answers.jsonl に保存される。

注意: Ragas は API 変更が多い。本スクリプトは ragas 0.2 系を想定したサンプルであり、
      実行環境のバージョンに合わせて import と evaluate 呼び出しを調整すること。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "level1"))
from run_level1 import embed, load_cases, rerank, search  # noqa: E402

VLLM_BASE_URL = os.environ["VLLM_BASE_URL"]
VLLM_MODEL = os.environ["VLLM_MODEL"]
VLLM_API_KEY = os.getenv("VLLM_API_KEY", "dummy")
GOLDEN_PATH = os.getenv("GOLDEN_PATH", "../../eval/golden_dataset.sample.jsonl")
RETRIEVE_K = int(os.getenv("RETRIEVE_K", "20"))
FINAL_K = int(os.getenv("FINAL_K", "5"))
ANSWERS_PATH = os.getenv("ANSWERS_PATH", "answers.jsonl")
NO_ANSWER_PHRASE = "資料からは回答できません"

# deploy/plan2/rag-api/main.py と同一のプロンプト(変更したら両方直すこと)
PROMPT = """以下のコンテキストのみに基づいて日本語で回答してください。
コンテキストに答えが含まれない場合は、推測せず「資料からは回答できません」と答えてください。

# コンテキスト
{context}

# 質問
{question}"""


def generate_answer(question: str, contexts: list[str]) -> str:
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(base_url=VLLM_BASE_URL, api_key=VLLM_API_KEY,
                     model=VLLM_MODEL, temperature=0)
    context = "\n\n".join(f"[{i + 1}] {c}" for i, c in enumerate(contexts))
    return llm.invoke(PROMPT.format(context=context, question=question)).content


def run_pipeline(cases: list[dict]) -> list[dict]:
    records = []
    for case in cases:
        # 会話文脈依存(TC09)は履歴を質問に前置してから検索する(簡易版)
        question = case["question"]
        if case.get("history"):
            prefix = " / ".join(m["content"] for m in case["history"])
            question = f"{prefix} という文脈での質問: {question}"

        chunks = rerank(question, search(embed(question), RETRIEVE_K), FINAL_K)
        contexts = [c.get("page_content", "") for c in chunks]
        answer = generate_answer(question, contexts)
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
