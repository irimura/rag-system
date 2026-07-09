# テストデータ集 — Vector store 投入用コーパスと評価用データセット

RAG のテストに使うデータは用途で 3 種類に分かれます。いずれも**無償で入手可能な公開データ**です(URL・ライセンスは 2026-07 時点で確認済み。利用前に配布元の最新条件を確認してください)。

| 用途 | 内容 | 本書の節 |
|---|---|---|
| A. コーパス | Vector store に投入する文書本体 | §1 |
| B. 評価用 QA データセット | 質問と正解が対になったデータ(ゴールデンデータセットの代替/補完) | §2 |
| C. コンポーネント選定ベンチマーク | Embedding / Reranker のモデル比較用 | §3 |

## 1. Vector store 投入用コーパス(公開文書)

日本語 RAG の動作検証・負荷試験に適した公開文書ソース。**性質の異なるものを混ぜる**(構造化された法令 + 長文の白書 + 雑多な記事)と、チャンク分割や検索の弱点が見つかりやすい。

| ソース | 内容・規模 | 形式 | ライセンス | URL |
|---|---|---|---|---|
| **e-Gov 法令検索(法令 API)** | 全法令(数千件)。条・項の構造が明確で TC01/TC03(条番号)向き | XML / JSON API | 法令は著作権の目的とならない(著作権法 13 条) | https://laws.e-gov.go.jp/ (API: https://laws.e-gov.go.jp/apitop/) |
| **総務省 情報通信白書** | 年度版 300〜500 ページ。図表・統計が多く TC05(表・数値)/TC06(年度)向き | PDF / HTML | 政府標準利用規約(CC BY 4.0 互換) | https://www.soumu.go.jp/johotsusintokei/whitepaper/ |
| **IPA 公開資料** | 情報セキュリティ白書、中小企業向けガイドライン等。技術文書の代表 | PDF | ページ記載の利用条件(多くは出典明記で利用可) | https://www.ipa.go.jp/security/reports/ |
| **デジタル庁 政策文書** | 重点計画・ガイドライン群 | PDF / HTML | 政府標準利用規約(CC BY 4.0 互換) | https://www.digital.go.jp/ |
| **Wikipedia 日本語版ダンプ** | 百科事典記事 約 140 万件。大規模負荷試験・一般知識 QA 向き | XML dump(要 wikiextractor 等で前処理) | CC BY-SA 4.0 | https://dumps.wikimedia.org/jawiki/ |
| **青空文庫** | 著作権切れ文学作品 1.7 万件超。長文・旧仮名の頑健性試験向き | テキスト(ルビ記法) | パブリックドメイン中心(作品毎に確認) | https://www.aozora.gr.jp/ (一括: https://github.com/aozorabunko/aozorabunko) |
| **livedoor ニュースコーパス** | ニュース記事 7,367 件・9 カテゴリ。日本語 NLP の定番 | テキスト | CC BY-ND 2.1 JP(**改変禁止** — 社内評価用途に留める) | https://www.rondhuit.com/download.html |
| **国会会議録検索システム API** | 国会の発言録。話し言葉・長文 | JSON API | 利用規約に従い利用可 | https://kokkai.ndl.go.jp/api.html |

### 推奨コーパスセット(段階別)

| 段階 | 構成 | 規模感 |
|---|---|---|
| 動作確認 | 情報通信白書 1 年度分 + 法令 10 本(例: 個人情報保護法、労働基準法) | 数百〜数千チャンク |
| 精度評価 | 上記 + IPA 資料 + livedoor コーパス(多ジャンル混在で誤ヒットを検出) | 数万チャンク |
| 負荷・規模試験 | 上記 + Wikipedia ダンプ(全件または カテゴリ抽出) | 数十万〜数百万チャンク |

> **取り込み時の注意:** PDF は抽出品質を必ず目視サンプリングする([rag-components.md §1](rag-components.md))。Wikipedia ダンプは wikiextractor(MIT)等で本文抽出してから投入する。

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

1. JSQuAD 検証データのユニークなコンテキスト(Wikipedia 段落)を抽出し、Vector store に投入する(約 1,700 記事)
2. 質問を評価クエリ、`answers` を ground truth、コンテキスト ID を evidence として [evaluation-spec.md §3](evaluation-spec.md) の JSONL 形式に変換する
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
