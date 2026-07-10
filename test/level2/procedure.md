# レベル2 手順書 — Generation 評価(Ragas / 該当なし正答率)

- 目的: End-to-End の回答品質(捏造の有無・正答性・論点適合)を LLM-as-a-Judge で採点する
- 前提: **レベル1 合格後に実行する**(検索が悪い状態での生成評価は無意味)
- 指標の定義と合否基準: [evaluation-spec.md](../../docs/evaluation-spec.md) §2.2 / §6

## 1. 前提条件

- [ ] [レベル1](../level1/procedure.md) が合格している
- [ ] Node A の vLLM が稼働している(judge としても利用するため)
- [ ] rag-api が稼働している(`curl http://localhost:8000/health`)

## 2. 実行環境の準備(初回のみ、Node B 上)

```bash
cd rag-system/test/level2
python3 -m venv .venv && source .venv/bin/activate
pip install httpx ragas langchain-openai langchain-huggingface datasets
pip freeze > requirements.lock.txt   # Ragas は API 変更が多いため必ずバージョンを固定する
```

## 3. 実行手順

```bash
export VLLM_BASE_URL=http://${node_a}:8080/v1
export VLLM_MODEL=${served_model_name}
export VLLM_API_KEY=${vllm_api_key}

# 全件評価(回答生成 -> TC07 判定 -> Ragas 採点)
python run_level2.py

# 回答生成のみ(Ragas を使わず、生成結果 answers.jsonl を目視確認したい場合)
python run_level2.py --generate-only
```

処理の流れ:

1. ゴールデンデータセットの各ケースについて、検索(レベル1 と同一ロジック)→ 生成(vLLM、rag-api と同一プロンプト)を実行し、`answers.jsonl` に保存
2. **TC07(該当なし)**: 回答に「資料からは回答できません」が含まれるかを機械判定し、該当なし正答率を算出
3. **answerable ケース**: Ragas で Faithfulness / Answer Correctness 等を採点(judge = vLLM、embeddings = TEI)

出力例:

```
=== レベル2: Generation 評価 ===
該当なし正答率 (TC07)  : 1.000 (1/1)
Faithfulness           : 0.91
Answer Correctness     : 0.78
...
```

## 4. 判定

| 指標 | 初期目標 | 未達時の一次対応 |
|---|---|---|
| Faithfulness | ≥ 0.90 | 捏造が発生。プロンプトの制約強化・コンテキスト件数削減・Rerank しきい値導入 |
| Answer Correctness | ≥ 0.75 | 正解に届かない。検索品質(レベル1 のカテゴリ別)とプロンプトを確認 |
| 該当なし正答率(TC07) | ≥ 0.90 | 無理に回答している。[cases/TC07_unanswerable.md](../cases/TC07_unanswerable.md) で深掘り |

## 5. 記録と注意点

- 実験管理表(`eval/experiments.md`)にスコアを追記し、`answers.jsonl` を実験 ID 付きで保存する(後から judge の採点を目視検証できるように)
- **LLM-as-a-Judge のスコアは絶対値でなく相対比較に使う**。judge モデルや Ragas バージョンを変えたらベースラインから取り直す
- スコアが疑わしいケースは `answers.jsonl` の該当行を目視確認する(judge の誤採点は一定数ある)
- 本スクリプトは検索+生成を rag-api と同一ロジックで再現している(Ragas がコンテキスト原文を必要とするため)。rag-api 経由の E2E 確認は `cases/` の手順書(WebUI 操作)で補完する
