# PDF変換プロダクト説明資料

## 結論

サンプル比較では、用途が重なるプロダクトを一つに決め打ちしない。文字埋込みPDFの速度基準にAnyDoc、総合基準にDocling、複雑な表・多段組みにMinerU、スキャンと日本語OCRにPaddleOCRを置く。Docling VLM、olmOCR、MarkerはVLM・高精度系の比較対象とする。YomiTokuは非商用検証に限定し、NDLOCRは現行環境との互換性を確認する探索枠とする。

公開ベンチマークは対象言語、文書、ハードウェアが一致しないため、順位の根拠にはしない。本データセットを同じNode Aで実測した結果を選定根拠とする。

## 比較表

| 識別子 | 方式 | 文字埋込み / スキャン | 主な出力 | 表・数式・図 | 日本語 | GPU | ライセンスと無償利用条件 | 公開値・速度目安 | 導入 |
|---|---|---|---|---|---|---|---|---|---|
| `docling` | PDF解析＋MLレイアウト解析＋OCR | 両方 | Markdown、JSON、HTML等 | TableFormer、数式・画像参照 | OCRエンジン次第。本検証で実測 | 任意 | コードMIT。モデルごとの条件も確認 | 公式は特定環境の一律速度を保証しない | 中 |
| `docling-vlm` | ページ画像→公開VLM | 両方 | Markdown、JSON等 | DocTagsで構造化 | 日本語公開ベンチなし | 既定GPU | DoclingはMIT。Granite DoclingはApache-2.0、SmolDoclingはモデルカード確認 | 256M級モデル。実測必須 | 中〜高 |
| `docling-vlm-commercial` | ページ画像→非公開VLM API | 両方 | Markdown | モデルとプロンプトによる | 公開情報を記載しない。本データセットで実測 | vLLM側で使用 | DoclingはMIT。非公開モデルの契約、入力、生成物、費用条件を別途確認 | 公開値を比較根拠にせず実測 | 高 |
| `mineru` | レイアウト・OCR・表・数式の複合パイプライン | 両方 | Markdown、JSON、LaTeX | 対応 | 109言語を掲げるが日本語個別値は未公表 | 推奨 | 現行配布物はAGPL-3.0。配布・ネットワーク提供時は法務確認 | olmOCR-Benchの公開比較あり。日本語専用値ではない | 高 |
| `paddleocr` | OCR＋MLレイアウト・表解析 | 両方。特にスキャン | Markdown、JSON、HTML表 | 表、式、図領域 | PP-OCRv5は日本語対応。公式の日本語評価列あり | 既定GPU | Apache-2.0 | 公式値は内部評価集合を含むため本PDFで再測定 | 高 |
| `anydoc` | Rust製の決定的パーサー | 文字埋込みのみ / 不可 | GFM | 埋込みテキスト・表。画像は代替文 | OCRなし | 不要 | MIT | 公式混合文書ベンチ中央値4.4 ms。ただしPDFだけの値ではない | 低 |
| `yomitoku` | 日本語向けOCR・文書解析ML | 主にスキャン | Markdown、JSON | 表、図、縦書き | 日本語特化 | 任意 | **CC BY-NC-SA 4.0。商用利用不可** | 日本語個別の再現可能な公開値は確認できず | 中 |
| `ndlocr` | NDL資料向けOCR・レイアウト解析 | スキャン | XML、TXT等（本手順でMarkdown化） | 読み順・縦書き。Markdown表復元は限定的 | 日本語特化 | 対応構成による | CC BY 4.0。表示義務あり | NDL資料向け評価。今回の実文書では実測 | 高 |
| `olmocr` | 7B VLM | 両方 | Markdown、Dolma | 表、数式、手書き、図周辺 | 多言語だが日本語専用値なし | 必須 | Apache-2.0 | olmOCR-Bench総合82.4±1.1（v0.4.0。日本語専用値ではない） | 高 |
| `marker` | MLレイアウト・OCR＋任意LLM | 両方 | Markdown、JSON、HTML | 表、数式、画像 | 多言語。日本語専用値なし | 既定GPU | コードGPL-3.0。モデル重みは修正AI Pubs OpenRAIL-Mで、研究・個人・一定規模未満の企業は無償 | olmOCR-Bench掲載値76.1±1.1（v1.10.1。日本語専用値ではない） | 中 |

GFMはGitHub Flavored Markdown、VLMは画像と言語を扱う視覚言語モデルを指す。「未公表」は、2026年8月6日に確認した公式資料で今回と同じ日本語PDF集合の値を確認できなかったという意味であり、精度が低いという意味ではない。

## 各プロダクトの特徴

### Docling / Docling VLM

標準パイプラインはPDFバックエンド、レイアウト検出、OCR、TableFormerを組み合わせる。VLMパイプラインはページ画像から構造を生成するため、読み順が崩れる文書を救済できる一方、生成誤りも評価対象になる。公式文書は `standard` と `vlm` を別pipelineとして説明し、VLMの既定をGranite Doclingとしている（[Doclingパイプライン公式文書](https://docling-project.github.io/docling/examples/agent_skill/docling-document-intelligence/pipelines/)）。コードの条件は[MITライセンス](https://github.com/docling-project/docling/blob/main/LICENSE)である。

`docling-vlm-commercial` は、OpenAI互換APIを提供する非公開VLMを使う追加比較枠である。モデル名とAPIキーを成果物へ残さず、内部承認済み別名で結果を識別する。モデルの非公開性は利用不可の理由にならないが、画像入力、Markdown応答、契約条件を確認できない場合は実行しない。DoclingはvLLMを含むOpenAI互換のリモートVLMに対応する（[DoclingリモートVLM公式文書](https://docling-project.github.io/docling/usage/vision_models/)）。

### MinerU

文字抽出、OCR、レイアウト、表、数式を組み合わせた高精度型である。複雑な紙面に向くが、モデル容量と依存関係が大きい。現行公式リポジトリはパイプラインとVLMの両方式、Markdown/JSON/LaTeX出力、109言語対応を掲げる（[MinerU公式リポジトリ](https://github.com/opendatalab/MinerU)）。現行PyPIメタデータはAGPL-3.0を示すため、以前のApache-2.0という紹介を流用しない。

### PaddleOCR PP-StructureV3

OCR、向き補正、レイアウト、表認識などを一つのパイプラインとして実行する。本検証ではPP-OCRv5系の日本語認識を使い、L4 GPUを既定にする。PP-OCRv5公式資料は日本語を対象文字種に含め、日本語列を持つ評価表を公開している（[PP-OCRv5公式資料](https://paddlepaddle.github.io/PaddleOCR/v3.0.0/en/version3.x/algorithm/PP-OCRv5/PP-OCRv5.html)）。実行方法は[PP-StructureV3公式手順](https://paddlepaddle.github.io/PaddleOCR/v3.0.3/en/version3.x/pipeline_usage/PP-StructureV3.html)を基準にする。

### AnyDoc

FirecrawlのAnyDocはRust製で、MLモデルを使わず文字埋込みPDFを直接解析する。公式資料は中央値4.4 msを掲げるが、14形式混合のベンチマークであり、PDFだけの性能ではない。画像のみのPDFは明示的に未対応である（[AnyDoc公式リポジトリ](https://github.com/firecrawl/anydoc)）。したがって、スキャンPDFの失敗は製品不良ではなく適用範囲外として集計する。

### YomiToku

日本語の文書画像、縦書き、表を対象とする。コードとモデルは[公式リポジトリ](https://github.com/kotaro-kinoshita/yomitoku)で公開されるが、CC BY-NC-SA 4.0である。非商用条件に合う検証だけで使用し、商用PoCや社内業務が「非商用」に当たるかを独断で判断しない。

### NDLOCR

国立国会図書館資料向けに開発された日本語OCRである。公式発表はver.2をCC BY 4.0で公開したと明記する（[NDLラボ公式発表](https://lab.ndl.go.jp/news/2023/2023-07-12/)）。古い依存関係や独自出力を含むため、Ubuntu 24.04 / Python 3.11での互換性をサンプル前に確認する。

### olmOCR

7B VLMでページをMarkdownへ変換する。公式は表、数式、手書き、多段組みへの対応と、7,000超のテストからなるolmOCR-Benchを公開する（[olmOCR公式リポジトリ](https://github.com/allenai/olmocr)）。L4 24 GBでは量子化・FP8モデルを使い、同じGPUでほかのモデルを同時起動しない。

### Marker

レイアウト、OCR、表、数式を扱う高速変換器である。コードはGPL-3.0だが、公式説明ではモデル重みに別条件がある（[Marker公式リポジトリ](https://github.com/datalab-to/marker)）。「GPLなので商用利用も常に無条件」とまとめず、利用主体とモデル条件を確認する。

## 選定上の注意

- 日本語OCRの公開値がないプロダクトは、本検証のキーワード一致率と目視で比較する。
- 出力文字数が多いだけでは精度が高いと判断しない。重複、ヘッダー混入、幻覚を確認する。
- VLM系の速度とVRAMはモデル、量子化、画像解像度で変わる。公開モデルはモデル名とバージョンを結果へ記録する。非公開モデルは内部承認済み別名を記録し、実モデル名との対応をアクセス制御された別台帳で管理する。
- ライセンス判断はソフトウェア本体、モデル重み、依存物を分ける。本資料は法的助言ではない。
