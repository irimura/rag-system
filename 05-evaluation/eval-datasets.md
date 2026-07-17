# 評価用データセット

RAG の評価パイプライン、コンポーネント比較、合成 QA の補完に使える公開データをまとめます。
Vector DB へ投入する文書候補は [コーパス候補データセット](../04-corpus/corpus-datasets.md) を参照してください。

## 2. 評価用 QA データセット(質問 + 正解付き)

**「コーパスと QA が対で揃っている」**公開データセット。自ドメインのゴールデンデータセットを作る前に、これらで評価パイプライン自体(スクリプト・指標計算)を検証するのが標準的な進め方。

| データセット | 内容 | 規模 | ライセンス | URL |
|---|---|---|---|---|
| **JSQuAD**(JGLUE) | Wikipedia 記事(コンテキスト付き)+ 抽出型 QA。**コンテキストをコーパス、質問を評価クエリにそのまま使える**第一候補 | 訓練 6.3 万 / 検証 4.4 千問 | CC BY-SA 4.0 | https://github.com/yahoojapan/JGLUE |
| **JAQKET** | クイズ形式 QA(答えが Wikipedia 記事名)。オープンドメイン検索向き | 約 2.4 万問 | 開発データ: CC BY-SA 4.0(訓練データは研究目的配布 — 条件確認) | https://www.nlp.ecei.tohoku.ac.jp/projects/jaqket/ |
| **JQaRA** | JAQKET 由来の質問 + Wikipedia パッセージ 100 件に関連性ラベル。**Retriever/Reranker 評価専用**に設計 | 1,667 問 × 100 件 | CC BY-SA 4.0 | https://huggingface.co/datasets/hotchpotch/JQaRA |
| **MIRACL(ja)** | 多言語検索ベンチマークの日本語サブセット。Wikipedia + 人手関連性ラベル | 数千クエリ | Apache-2.0 | https://huggingface.co/datasets/miracl/miracl |
| **JaCWIR** | Web ページ(タイトル + 概要)ベースの日本語検索評価。Wikipedia 以外の文体 | 5 千問 | 配布ページの条件を確認(評価目的) | https://huggingface.co/datasets/hotchpotch/JaCWIR |

### JSQuAD を使ったパイプライン検証の流れ(標準手順)

1. JSQuAD 検証データのユニークなコンテキスト(Wikipedia 段落)を抽出し、Vector DB に投入する(約 1,700 記事)
2. 質問を評価クエリ、`answers` を ground truth、コンテキスト ID を evidence として [評価仕様 §3](evaluation-spec.md) の JSONL 形式に変換する
3. レベル1(Hit Rate / MRR)→ レベル2(Ragas)を実行し、評価スクリプトの動作と指標の妥当性を確認する
4. パイプラインが確認できたら、自ドメイン文書 + 人手ゴールデンデータセットでの本評価に移る

> JSQuAD は「コンテキストが与えられる前提」の抽出型 QA のため、全体を検索対象にすると難易度が上がる(それ自体が Retriever の良い試験になる)。該当なしケース(TC07)は含まれないので、**別コーパスの質問を混ぜて自作**する。

## 3. コンポーネント選定ベンチマーク(モデル比較用)

自前評価の前段で、Embedding / Reranker の候補モデルを絞るのに使う公開リーダーボード・ベンチマーク。

| ベンチマーク | 対象 | URL |
|---|---|---|
| **JMTEB** | 日本語 Embedding(検索・分類・STS 等) | https://github.com/sbintuitions/JMTEB |
| **JQaRA** | 日本語 Retriever / Reranker | 上記 §2 |
| **JaCWIR** | 日本語 Retriever / Reranker(Web 文体) | 上記 §2 |
| MTEB Leaderboard | 多言語 Embedding(参考) | https://huggingface.co/spaces/mteb/leaderboard |

## 4. 合成データによる補完(Ragas TestsetGenerator)

公開データセットで賄えない**自ドメイン風の質問量産**には、Ragas の TestsetGenerator を使う(LLM は vLLM を指定 — 無償で完結)。

```python
from ragas.testset import TestsetGenerator
# generator_llm に vLLM(OpenAI 互換)、embeddings に TEI を指定
generator = TestsetGenerator(llm=generator_llm, embedding_model=embeddings)
testset = generator.generate_with_langchain_docs(docs, testset_size=100)
```

- 生成された QA は**必ず人手レビュー**してから採用する(質問が不自然・正解が誤りのケースが一定数出る)
- 合成データは「量の確保」、人手データは「実利用の代表性」と役割を分けて両方使うのが標準
