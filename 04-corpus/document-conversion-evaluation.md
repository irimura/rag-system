# 文書変換ツール選定 評価レポート

> 本レポートは、PDF / HTML / PPTX の変換ツールから PoC 主候補を選び、検証計画を定めます。採用は PoC 合格後に確定します。
>
> PoC では、隔離 venv、一時スクリプト、依存 lock、モデルキャッシュ、評価ハーネスを作成します。使用したパッケージ版、モデル revision、lock を保存します。
>
> 本番ファイルの変更は PoC 合格後に行います。対象は `prepare_stage.sh`、`common.py`、`requirements.txt`、関連ドキュメントです。
>
> 調査時点: 2026年7月。採用前にライセンス、ベンチマーク、API 仕様を一次情報で再確認します。コード例は PoC で版を固定して検証します。
>
> 改訂履歴:
> - 2026-07-24 初版
> - 2026-07-24 一次レビュー反映
> - 2026-07-24 二次レビュー反映
> - 2026-07-24 三次レビュー反映。承認条件を解消
> - 2026-07-24 ワークフローパターンを追記

## 1. 背景と目的

本リポジトリは vLLM と LangChain を使う日本語 RAG システムです。コーパス取得と ingest を分離しています。

総務省の情報通信白書と IPA 公開資料は、前処理せず `raw/` から `documents/{whitepaper,ipa}/` へ配置します。ingest 時は `PyPDFLoader` でページ単位に抽出します。

[plan2 common.py](../03-deployment/plan2/rag-api/common.py) を参照してください。plan1 と plan3 の `load_documents`、`split_documents` も同等です。

pypdf は表、段組み、スキャン PDF の抽出を誤ることがあります。[構成要素解説](../06-tuning/README.md)でも抽出品質を既知課題としています。

本レポートは無償利用可能な変換ツールを比較し、PoC 主候補と検証計画を定めます。

### スコープ

- 対象形式: PDF、HTML、PPTX
- 品質評価: PDF のみ
- 成立確認: HTML、PPTX

現行の `load_documents` は `.pdf`、`.md`、`.txt` のみを読み込みます。HTML と PPTX の取り込み経路はありません。

---

## 2. 結論

- PoC 主候補は Docling とする。
  - MIT ライセンスでローカル実行できる。
  - PDF、HTML、PPTX、DOCX、XLSX を単一 API で扱える。
  - レイアウトと表構造を推定できる。
  - pypdf より優れるかは PoC で確認する。
- 多形式の文書は、前処理で Markdown に統一する。
  - ingest は既存の `TextLoader` を利用できる。
  - HTML、PPTX 用の Loader 追加が不要になる。
- チャンク方式は案Aと案Bを比較する。
  - 案Aは Markdown を既存 splitter で分割する。
  - 案Bは DoclingDocument JSON を `HybridChunker` で分割する。
- MarkItDown と MinerU を比較対象にする。
  - MarkItDown は軽量比較対象とする。
  - MinerU は高機能比較対象とし、先にライセンスを確認する。
- 公開ベンチマークは参考情報に限定する。
  - 対象言語、文書、版、指標が異なるため、単純な順位比較はしない。
  - 最終判断は本件コーパスの実測に基づく。
- パース処理は取得用 venv に分離する。
  - モデルと依存は NAT 開放中に取得する。

---

## 3. 現状

| 工程 | 内容 |
|---|---|
| 取得 | 白書と IPA は `raw/` へ保存する。e-Gov は XML を Markdown に、Wikipedia は txt に変換する |
| 配置 | `prepare_stage.sh` が白書と IPA を `RAW_DIR` から配置する。laws と wikipedia は `PROCESSED_DIR` から配置する |
| 取り込み | `load_documents` が PDF、Markdown、txt を読み込む。HTML と PPTX は対象外 |
| 分割 | `RecursiveCharacterTextSplitter` を使う。既定値は 500 文字、100 文字 overlap。日本語 separator を設定済み |
| メタデータ | 案2/3は `documents/<group>/` の第1階層から `group` を設定する。不正なパスは `SystemExit` で停止する |

統合時は `source` と `group` を維持します。

前処理は [preprocess_egov.py](scripts/preprocess_egov.py) を雛形にします。このスクリプトは環境設定、入出力引数、mtimeによるスキップ、出典付与を実装しています。

---

## 4. 多形式変換ツール比較

### 4-1. 候補一覧

GitHub star などの普及度は補助情報です。実運用件数や品質を示すものではありません。値は2026-07-24閲覧時の概算です。

| ツール | 入力形式 | ライセンス | 日本語 | 構造化 | 実行環境 | オフライン | 補助情報 |
|---|---|---|---|---|---|---|---|
| **Docling** | PDF、HTML、PPTXほか | コードMIT。モデルは個別確認 | 公式比較値なし | HeronとTableFormer | CPU、GPU | ◎ | 約63.7k star |
| **MarkItDown** | PDF、HTML、PPTXほか | MIT | 公式比較値なし | レイアウト推定なし | CPU | ◎ | 約168.6k star |
| **Unstructured** | 30形式以上 | OSSはApache-2.0。商用APIは別提供 | 公式比較値なし | 公式比較値なし | CPU | ○ | RAGで広く利用 |
| **Apache Tika** | 1000形式以上 | Apache-2.0 | 公式比較値なし | プレーンテキスト | CPU、Java | ◎ | 長期実績 |
| **Marker** | PDF、Office、HTMLほか | コードApache-2.0。重みに商用制限 | 公式比較値なし | 表、数式、フォーム | GPU推奨 | ○ | olmOCR-Bench 76.1±1.1 |
| **MinerU** | PDF、画像、Office | 独自ライセンス。追加条件あり | 109言語OCR | 数式、読み順 | GPU推奨 | ○ | 要法務確認 |
| **olmOCR** | PDF、画像 | Apache-2.0 | 英語中心 | スキャンOCR | GPU | ○ | olmOCR-Bench 82.4±1.1 |
| **PyMuPDF4LLM** | PDF | AGPL-3.0または商用 | 公式比較値なし | Markdown | CPU | ◎ | 要法務確認 |

Markerの重みは modified AI Pubs Open Rail-M です。研究、個人、資金調達額または売上が200万USD未満のスタートアップは無償です。それ以外の商用利用には別ライセンスが必要です。READMEにはGPL表記も残るため法務確認します。

MinerUは2026年4月に独自ライセンスへ変更しました。MAUが1億を超える場合、または月間総収益が2,000万USDを超える場合は別ライセンスが必要です。第三者向けオンラインサービスには表示義務があります。HTMLは別プロジェクトのMinerU-HTMLが扱います。

olmOCR-Benchの値は、olmOCR v0.4.0が82.4±1.1、Marker 1.10.1が76.1±1.1です。英語中心の評価です。

### 4-2. 単機能の選択肢

- HTML
  - Trafilatura: Apache-2.0
  - Pandoc: GPL-2.0
- PPTX
  - python-pptx: MIT
- PDF
  - pdfminer.six、pypdf、pdfplumber: MIT系
  - 構造化 Markdown は出力しない。

### 4-3. 評価上の注意

1. 公開評価から日本語性能の順位は決めない。
   - olmOCR-Bench は英語中心である。
   - OmniDocBench v1.0 は1,651ページ、10文書種、5レイアウト、5言語を含む。
   - OmniDocBenchには28種のblock注釈と4種のspan注釈がある。
   - 評価条件が異なるため、本件コーパスで比較する。
2. 画像化された表は、どの OCR でも難しい。
3. コードとモデル重みのライセンスを分けて確認する。
   - Docling、MarkItDown、Unstructured OSS、Tika、olmOCRの本体コードは MIT または Apache-2.0 である。
   - モデル重みはモデルごとに確認する。
   - PyMuPDF4LLM、MinerU、Markerは採用前に法務確認する。

---

## 5. Docling の Chunking とフレームワーク連携

Docling は文書変換とチャンキングを提供します。

### 5-1. HierarchicalChunker

`DoclingDocument` の要素ごとにチャンクを生成します。既定ではリスト項目をまとめ、見出しとキャプションをメタデータへ追加します。

### 5-2. HybridChunker

階層チャンキングの結果をトークン数で調整します。

1. 上限を超えたチャンクを分割する。
2. 文脈が同じ小さなチャンクを結合する。

| パラメータ | 役割 |
|---|---|
| `tokenizer` | 埋め込みモデルに対応する `BaseTokenizer` 実装。モデル名の文字列は不可 |
| `max_tokens` | トークン上限。`HuggingFaceTokenizer` 側に設定 |
| `merge_peers` | 小さな隣接チャンクを結合。既定 `True` |
| `repeat_table_header` | 分割した表へヘッダを再掲。既定 `True` |
| `omit_header_on_overflow` | 上限超過時にヘッダを省略。既定 `False` |

```python
from transformers import AutoTokenizer
from docling.chunking import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer

tokenizer = HuggingFaceTokenizer(
    tokenizer=AutoTokenizer.from_pretrained(
        "intfloat/multilingual-e5-large",  # 本システムの埋め込みモデルと一致させる
        local_files_only=True,             # 事前取得済みキャッシュを使用（オフライン方針）
    ),
    max_tokens=512,                        # e5 系の上限
)
chunker = HybridChunker(
    tokenizer=tokenizer,
    merge_peers=True,
    repeat_table_header=True,
)
chunks = chunker.chunk(dl_doc=docling_document)
for c in chunks:
    text = chunker.contextualize(chunk=c)  # メタデータ強化表現を埋め込みへ
```

主な効果は次のとおりです。

- トークン上限を守る。
  - 現行 splitter は文字数で分割する。
  - `HybridChunker` は埋め込みモデルのトークナイザで分割する。
- 見出し文脈を追加する。
  - `contextualize()` が検出済みの見出しとキャプションを追加する。
  - 品質は見出し検出と階層推定に依存する。
- 表ヘッダを再掲する。
  - `repeat_table_header` が分割後の各チャンクへヘッダを追加する。
  - 表を誤認識した場合は修復できない。

### 5-3. LangChain 連携（`langchain-docling`）

`DoclingLoader` は `DOC_CHUNKS` と `MARKDOWN` の2モードを提供します。どちらも `lazy_load()` に対応します。

```python
# DOC_CHUNKS（既定）: 変換とチャンキングを一気通貫
from langchain_docling import DoclingLoader
from langchain_docling.loader import ExportType

loader = DoclingLoader(
    file_path="whitepaper.pdf",
    export_type=ExportType.DOC_CHUNKS,
    chunker=chunker,   # 上で構築した HybridChunker
)
docs = loader.load()   # 1 chunk = 1 LangChain Document

# MARKDOWN: 文書まるごと1 Document、分割は自前
loader = DoclingLoader(file_path="whitepaper.pdf", export_type=ExportType.MARKDOWN)
```

`dl_meta` は次の情報を保持します。

- `doc_items`: `self_ref`、`parent`、`label`、`prov`
- `prov`: `page_no`、`bbox`、`charspan`
- `headings`
- `origin`: `mimetype`、`binary_hash`、`filename`

この情報を使うと、ページ番号と座標を出典にできます。`source`、`group` と併存できるかは PoC で確認します。

### 5-4. LlamaIndex 連携（参考）

LlamaIndex では `DoclingReader` と `DoclingNodeParser` を利用できます。JSON は DoclingDocument を可逆保存できます。Markdown は非可逆です。

本リポジトリでは LlamaIndex を使いません。ただし、JSONによる可逆保存は案Bでも利用できます。

---

## 6. チャンキング方式

`HybridChunker` には DoclingDocument が必要です。Markdownだけを保存すると、レイアウトや表の構造情報を失います。JSONを併存すれば構造を保持できます。

| 観点 | 案A: MD＋見出し分割 | 案B: MD＋JSON＋HybridChunker |
|---|---|---|
| 前処理出力 | `processed/**/*.md` | `processed/**/*.md` と DoclingDocument JSON |
| ingest 側の分割 | `MarkdownHeaderTextSplitter` → `RecursiveCharacterTextSplitter` | JSON から `HybridChunker` |
| ingest 依存追加 | なし | `docling-core[chunking]`と推移依存。増分は実測 |
| トークン基準分割 | 個別実装が必要 | 標準機能 |
| 見出し文脈の付与 | 手実装が必要 | `contextualize()`。精度は見出し検出に依存 |
| 表のチャンク跨ぎ | ヘッダと行が分離し得る | `repeat_table_header`。表認識が前提 |
| `page_no` / `bbox` 出典 | ✕ 失われる | ◎ `dl_meta` で保持 |
| 成果物容量 | 小 | 大。要計測 |
| スキーマ互換性 | 影響なし | DoclingDocument更新の影響あり |
| 変換の追跡・再現 | md に出典を焼き込み | 変換設定・モデル revision・schema 版を JSON 側に記録可能 |
| 再変換コスト | 版更新時は md 再生成のみ | 版更新時に JSON 再生成が必要になる場合あり |
| 失敗時の調査 | md を目視すれば良い | JSON 構造の理解が必要 |
| セキュリティ / ロールバック | 影響小 | 依存増分の SBOM/CVE 確認、旧構成への戻し手順が必要 |

どちらの案でも、パース本体は取得用 venv に置きます。

案Bは次の結果で採否を決めます。

- イメージ増分
- 最大 RSS
- SBOMとCVE
- オフライン起動
- RAG評価

### 6-2. ワークフローパターン

ワークフローは、パース方式と受け渡し方式に分けて選びます。

- 既定パイプライン
  - HeronとTableFormerを使う。
  - 通常資料へ適用する。
- VLMパイプライン
  - self-hosted vLLMを使う。
  - スキャンや変換に失敗する資料へ限定する。

| パターン | パース | 受け渡し・分割 | ingest 側の依存追加 | provenance（page_no/bbox） | 位置づけ |
|---|---|---|---|---|---|
| P1 案A | 既定 | MD → 既存 TextLoaderとsplitter | なし | 原則失う | 最小変更。案Bと比較 |
| P2 案B | 既定 | MD＋JSON → HybridChunker | `docling-core[chunking]`等 | 条件付きで保持 | 高機能。効果と依存増分を実測 |
| P3 Loader＋chunks | 既定 | `DOC_CHUNKS`＋明示したHybridChunker | Docling本体、torch、モデル | 条件付きで保持 | 中間成果物なし。依存と再変換が課題 |
| P4 Loader＋MD | 既定 | `MARKDOWN` → 自前splitter | Docling本体 | 原則失う | 重い依存に対して利点が少ない |
| P6 取り込み先分割 | 任意 | 未分割MD → 取り込み先で分割 | 取り込み先依存 | 通常失う | Open WebUI案1bの標準経路 |
| P7 Full Context | 任意 | 文書全文をコンテキストへ投入 | 取り込み先依存 | 検索には不使用 | 小規模文書向け。通常RAGとは別方式 |

VLMはP5として、上記の受け渡し方式と組み合わせます。

| パース経路 | 適用対象 | 組み合わせ | 備考 |
|---|---|---|---|
| 既定パイプライン | 通常資料 | P1〜P7 | デジタルPDFではOCR無効も測定 |
| VLMパイプライン P5 | スキャン、変換失敗資料 | P1〜P7 | 低速でGPU負荷が高い。provenanceは出力形式に依存 |

本リポジトリではP1とP2を主に比較します。必要な資料だけP5を適用します。

---

## 7. Docling 採用の妥当性・実現性

### 妥当性

- 表、段組み、読み順の改善が期待できる。
  - pypdf は論理構造を復元しない。
  - Docling はレイアウト、読み順、表構造を推定する。
  - 優位性は本件コーパスで実測する。
- 複数形式を単一 API で扱える。
  - PDF、HTML、PPTX、DOCX、XLSXに対応する。
- 変換とチャンキングで同じ文書モデルを使える。

### 実現性

- 既存の前処理と同じ構成で追加できる。
  - MIT、Python 3.10以上、ローカル実行に対応する。
  - 隔離ネットワークと依存ピンの運用に適合する。
- OCRは既定で有効である。
  - デジタルPDFでは `do_ocr=False` も測定する。

### OCR / スキャン資料への対応（LLM 利用の可否）

- OCRエンジンにLLMは指定できない。
  - Tesseract、EasyOCR、RapidOCR、OcrMac、SuryaOCRなどを使う。
  - 対応エンジンは固定版で確認する。
- VLMは別のパース経路として利用する。
  - OpenAI互換エンドポイントを指定できる。
  - パース全体をVLMへ置き換える。
  - 次のコードは概念例である。固定版で動作確認する。

```python
import os

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import VlmConvertOptions, VlmPipelineOptions
from docling.datamodel.vlm_engine_options import ApiVlmEngineOptions, VlmEngineType
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.pipeline.vlm_pipeline import VlmPipeline

vlm_options = VlmConvertOptions.from_preset(
    "granite_docling",
    engine_options=ApiVlmEngineOptions(
        engine_type=VlmEngineType.API,
        url="http://llm-001:8000/v1/chat/completions",  # self-hosted vLLM
        headers={
            # 本システムの vLLM は --api-key 運用のため認証ヘッダが必要
            "Authorization": f"Bearer {os.environ['VLLM_API_KEY']}",
        },
        params={
            # vLLM 側の served model 名（--served-model-name）と一致させる
            "model": "ibm-granite/granite-docling-258M",
            "temperature": 0.0,
            "max_tokens": 8192,
            "skip_special_tokens": False,  # DocTags 出力に必要
        },
    ),
)
pipeline_options = VlmPipelineOptions(
    vlm_options=vlm_options,
    enable_remote_services=True,  # リモート送信の明示が必須
)
converter = DocumentConverter(
    format_options={
        InputFormat.PDF: PdfFormatOption(
            pipeline_cls=VlmPipeline,
            pipeline_options=pipeline_options,
        )
    }
)
```

公式生成サンプルには旧引数 `runtime_type` が残る場合があります。固定版のAPIリファレンスでは `engine_type` を確認します。

本システムではself-hosted vLLMへ接続します。外部APIは使いません。

PoCでは次を確認します。

- VLMモデルをserveできること
- presetとserved model名が一致すること
- 認証ヘッダが有効なこと

VLMは低速でGPU負荷が高いため、変換に失敗する資料へ限定します。

### リスク・留意点

| 項目 | 内容 | 対応方針 |
|---|---|---|
| 依存の重さ | torchとモデルで数百MB〜GB | パース本体は取得用venvに置く。案Bの増分は実測する |
| オフライン運用 | 初回にモデルを取得 | NAT開放中にprefetchし、キャッシュを固定する |
| スループット | 数百ページで分単位 | 出力を永続化し、mtimeで再処理を省く |
| 抽出品質 | 資料ごとに差がある | PyPDFLoaderと比較し、必要な資料だけ別経路へ切り替える |
| 依存ピン | `~=`を使用 | microまで指定する。例は `docling~=2.115.0` |
| 案1b | Open WebUI は `ingest.py`/`documents/` を持たない | 生成した Markdown を UI/API 経由でアップロードする運用として明記 |
| 表記正規化 | NFKC/neologdnは分割前に一度だけ実行 | Docling出力直後に正規化する |

`~=2.115` は2.x全体を許容します。マイナー系列を固定する場合は使いません。

---

## 8. 前処理ステップを選ぶ理由

| 観点 | 前処理ステップ（推奨） | ingest 時 Loader 置換 |
|---|---|---|
| 依存の分離 | パース依存を取得用venvへ分離 | 各ingestイメージへ依存を追加 |
| 冪等性・再現性 | `processed/`へ保存し、mtimeでスキップ | キャッシュがなければ再構築時に再変換 |
| 検証の粒度 | 前処理結果を資料単位で検収 | 資料単位の制御に追加実装が必要 |
| 多形式対応 | Markdownへ統一し、既存経路で取り込む | 形式別のLoaderとglobが必要 |
| 既存パターン | `preprocess_egov.py` / `preprocess_wikipedia.py` と同型で運用統一 | 既存の前処理規約から外れる |
| オフライン | NAT開放中にモデルを取得 | ingest時のモデル取得対策が必要 |

本リポジトリはバッチ取得、段階配置、フル再構築の順で運用します。このため前処理方式を推奨します。

次の要件がある場合は、キャッシュ付きLoader方式も検討します。

- 低遅延の増分更新
- 原本とインデックスの強い一貫性
- 変換成果物を保存しない運用

---

## 9. 検証方法（採用可否の判断根拠）

> PoCは隔離venvで実行します。合格条件、閾値、評価手順は開始前に固定します。

### 9-1. 評価資料と正解データの事前固定

- 評価資料を固定する。
  - デジタルPDF、スキャンPDF、縦書き、2段組、複雑表を各10ページ以上選ぶ。
- 正解データを人手で作る。
  - 文字転記
  - 読み順付きblock ID
  - 見出しlevel
  - 表の正規化HTML
  - `page_no`とbbox
- 表の評価方法を固定する。
  - TEDSまたはTEDS-Structを選ぶ。
  - MarkdownからHTMLへの変換規則を定める。
  - 結合セルと空セルの扱いを定める。

### 9-2. 測定指標

| 対象 | 指標 | 前提 |
|---|---|---|
| 文字抽出 | CER、欠落率、重複率 | 正解転記との比較 |
| 読み順 | block pair accuracy | 読み順付き block 注釈が必要 |
| 表 | TEDS または TEDS-Struct | 正解HTMLと変換規則が必要 |
| 見出し | level 付き precision/recall | 見出し注釈が必要 |
| 出典 | `page_no`正解率、bbox IoU | 構造出力を持つ候補のみ。別に合否判定 |
| RAG | Evidence Recall@4、MRR、nDCG | 本番ゴールデンデータでpaired比較 |
| 性能 | pages/s、最大 RSS、成果物サイズ、コンテナイメージ増分 | 同一 CPU・同一資料・同一 OCR 条件 |

サンプルゴールデンデータ10件は動作確認だけに使います。統計比較には本番ゴールデンデータを作成します。

同じ質問集合で Evidence Recall@4 をpaired比較します。標本数と信頼区間は、ベースラインと最小検出差から事前に決めます。

### 9-3. 比較系列

- パース方式
  - 現行 `PyPDFLoader`
  - `pdftotext`
  - Docling既定パイプライン。OCR有効と無効を測定
  - MarkItDown
  - MinerU。ライセンス確認後に実施
- チャンク方式
  - pypdfベースライン
  - 案A
  - 案B

`pdftotext` は別ベースラインとして扱います。現行システムの代用にはしません。

### 9-4. 合格条件

閾値と非劣性マージンはPoC開始前に設定します。必須条件をすべて満たすことを優先します。

- 必須条件
  - 節単位の本文欠落が0件
  - CERが現行pypdfに対して非劣性
  - Evidence Recall@4が有意に改善
- 参考条件
  - TEDS、読み順、見出し指標が改善
  - bbox IoUが基準を満たす

最小検出差は標本設計と同時に決めます。5ポイント改善は目安です。表構造とbboxは、対応する候補間だけで比較します。

### 9-5. その他の検証

1. 出典提示
   - `page_no`と`bbox`がチャンクへ到達すること
   - `source`と`group`を維持すること
   - `assign_group_metadata`と衝突しないこと
2. オフライン再現
   - NAT閉塞中に前処理が完走すること
   - `local_files_only=True`で動作すること
3. 案Bの成立性
   - イメージ増分、最大RSS、SBOM、CVEを確認すること
   - オフライン起動とJSONスキーマ互換性を確認すること
4. ライセンス
   - MinerUとMarkerを法務確認すること
5. VLM
   - VLMをserveできること
   - presetとserved model名が一致すること
   - 認証ヘッダが有効なこと

### 9-6. HTML / PPTX の成立確認

HTMLとPPTXは定量評価しません。固定したサンプルを目視確認します。

- PPTX
  - スライド順
  - スピーカーノート
  - 表
  - 図中テキスト
- HTML
  - 本文抽出
  - ナビゲーションとフッタの除外
  - 表
  - 見出し階層

実コーパスに追加された場合は、定量評価の要否を再判断します。

---

## 10. 採用後の変更

1. `preprocess_docs.py`を追加する。
   - [preprocess_egov.py](scripts/preprocess_egov.py)を雛形にする。
   - PDF、HTML、PPTXをMarkdownへ変換する。
   - NFKCとneologdnで正規化する。
   - 出典を追加する。
   - 案BではDoclingDocument JSONも保存する。
2. `prepare_stage.sh`を変更する。
   - whitepaperとipaの入力元を`PROCESSED_DIR`へ切り替える。
   - HTML、PPTX由来のグループを追加する。
3. チャンク分割を変更する。
   - 案AはMarkdown見出し分割と既存splitterを使う。
   - 案BはJSONとHybridChunkerを使う。
   - `source`と`group`を維持する。
   - 案1と案2/3へ個別に反映する。
4. 依存を追加する。
   - 取得側に`docling`とCPU版torchを追加する。
   - 案Bではingest側に`docling-core[chunking]`を追加する。
5. 関連ドキュメントを更新する。
   - [download.md](download.md)
   - [README.md](README.md)
   - [scripts/README.md](scripts/README.md)
   - [構成要素解説](../06-tuning/README.md)
   - [事前準備](prerequisites.md)
