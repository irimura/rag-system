# レベル1 手順書 — Retrieval 評価(Hit Rate / Evidence Recall / MRR / nDCG)

- 目的: Retriever(+Reranker)が正解根拠を上位に取得できているかを**決定的に**測定する
- 特徴: LLM 不要・数分で完了・毎回同じ結果。構成変更のたびに必ず実行する
- 指標の定義と合否基準: [evaluation-spec.md](../../docs/evaluation-spec.md) §2.1 / §6

## 1. 前提条件

- [ ] 案2 のサービス群が起動済み(`docker compose ps` で rag-api / qdrant / tei-embed / tei-rerank が Up)
- [ ] 評価用コーパスの取り込みが完了している(`ingest` 実行済み)
- [ ] ゴールデンデータセットが用意できている(サンプル: `eval/golden_dataset.sample.jsonl`)
- [ ] rag-api の構成パラメータ(チャンクサイズ / Embedding モデル / `RETRIEVE_K` / `RERANK_TOP_N` / `RERANK_THRESHOLD`)を実験管理表に記録した

## 2. 実行環境の準備(初回のみ、Node B 上)

```bash
cd rag-system/test/level1
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## 3. 実行手順

### 3.1 全件評価

```bash
# 既定値: rag-api は localhost:8000、データセットはサンプルを参照
python run_level1.py

# 実運用データセットを指定する場合
GOLDEN_PATH=../../eval/golden_dataset.jsonl python run_level1.py
```

出力例(このまま実験管理表に転記できる Markdown 行も出力される):

```
=== レベル1: Retrieval 評価 ===
対象: 9 ケース(answerable のみ。TC07 は対象外)
HitRate@20 (Rerank 前): 0.889
HitRate@4  (Rerank 後): 0.778
EvidenceRecall@20 (Rerank 前): 0.833
EvidenceRecall@4  (Rerank 後): 0.722
MRR@4                 : 0.712
nDCG@4                : 0.701
--- カテゴリ別 HitRate@4 ---
TC01_single_fact : 1.000 (1/1)
...
```

### 3.2 単一ケースの詳細確認(デバッグ / ケース手順書から利用)

```bash
python run_level1.py --case TC01-001 --verbose
# 取得チャンクの順位・本文冒頭と、一致した evidence 番号が表示される
```

## 4. 判定

| 指標 | 初期目標 | 未達時の一次対応 |
|---|---|---|
| HitRate@20(Rerank 前) | ≥ 0.90 | Retriever 側の問題。チャンク分割・Embedding・(案3)ハイブリッド化を見直す |
| HitRate@4(Rerank 後) | ≥ 0.85 | @20 が達成済みなら Reranker の問題。モデル・しきい値・候補数を見直す |
| EvidenceRecall@4 | 記録のみ | multi-hop で不足する根拠を特定し、候補数・チャンク分割を見直す |
| MRR@4 | ≥ 0.70 | 上位に押し込めていない。Rerank 導入/強化が定石 |

- **合格** → [レベル2](../level2/procedure.md) へ進む
- **不合格** → 検索側を 1 要素だけ変更して再実行(レベル2 には進まない)。カテゴリ別スコアで弱点観点を特定し、`cases/` の該当手順書で深掘りする

## 5. 記録

`eval/experiments.md`(なければ作成)に、スクリプトが出力する Markdown 行を追記する。あわせて変更した構成パラメータを備考に残す。

## 6. 他の案への読み替え

| 構成 | 読み替え |
|---|---|
| 案1(Chroma 組み込み) | 検索がプロセス内のため HTTP では叩けない。`run_level1.py` の検索部を `langchain_chroma` 直接呼び出しに差し替え、`deploy/plan1/app` の venv 上で実行する |
| 案3(OpenSearch) | 検索先を `http://localhost:9200/knowledge/_search` に変更し、BM25 + kNN + RRF(`deploy/plan3/rag-api/main.py` と同じロジック)を評価対象にする |
