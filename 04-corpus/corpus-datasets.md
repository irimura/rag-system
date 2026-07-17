# コーパス候補データセット

Vector DB へ投入する、日本語 RAG の動作検証・精度評価・負荷試験向け公開コーパスをまとめます。
評価用 QA、モデル比較、合成データは [評価用データセット](../05-evaluation/eval-datasets.md) を参照してください。

## 1. Vector DB 投入用コーパス(公開文書)

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

> 推奨セットの入手、前処理、固定グループへの配置、案1/1b/2/3への投入は [コーパス取り込み手順](README.md) を参照してください。

> **取り込み時の注意:** PDF は抽出品質を必ず目視サンプリングする([RAG 構成要素 §1](../06-tuning/rag-components.md))。Wikipedia ダンプは wikiextractor(MIT)等で本文抽出してから投入する。
