# 文書変換ツール選定 評価レポート（PDF / HTML / PPT → Markdown 前処理）

> 本レポートは**候補比較の上で PoC 主候補を選定し、検証計画を定める**評価であり、採用の確定と実装は未着手です。前処理スクリプトの追加、`prepare_stage.sh` / `common.py` の改修、依存追加、各ドキュメント更新は、PoC 実測（§9）の合格をもって着手します。
>
> 調査時点: 2026年7月。ライセンス条件・ベンチマーク値・API 仕様は変動するため、採用前に一次情報で再確認してください。コード例は版依存であり、PoC 時に版を固定して動作確認します。
>
> 改訂履歴:
> - 2026-07-24 初版
> - 2026-07-24 レビューエージェントの指摘を反映（Docling 現行 API への修正、OCR 既定値の訂正、無出典数値の削除、比較の対称化、測定可能な受け入れ基準の明文化）

## 1. 背景と目的

本リポジトリは vLLM + LangChain ベースの日本語 RAG システムのドキュメント/リファレンス集で、**コーパス取得（フェーズ 04）→ ingest 取り込み（フェーズ 03）**の二段構成です。

現状の PDF コーパス（総務省 情報通信白書・IPA 公開資料）は前処理なしで `raw/` から `documents/{whitepaper,ipa}/` へ配置され、ingest 時に **`PyPDFLoader`（pypdf）でページ単位に直接抽出**しています（[plan2 common.py](../03-deployment/plan2/rag-api/common.py)。plan1/plan3 の `load_documents` / `split_documents` も同等）。[構成要素解説](../06-tuning/README.md) §1 は「**抽出品質が全ての上限を決める**」と明記し、表・段組み・スキャン PDF で pypdf の抽出が壊れる問題を既に課題として挙げています。

本レポートは、この抽出品質の課題に対する無償利用可能な文書変換ツールを比較し、**PoC で実測すべき主候補と検証計画**を定めます。

### スコープ

取り込み対象を **PDF / HTML / PPT を同等**に扱う前提とします。ここで重要な制約があります —— **現行 `load_documents` は `.pdf` / `.md` / `.txt` しか glob しておらず、`.html` / `.pptx` の取り込み経路がそもそも存在しません**。

---

## 2. 結論（サマリ）

- **推奨: Docling を PoC 主候補とし、§9 の実測合格をもって採用を確定する。** MIT ライセンス・ローカル実行で PDF/HTML/PPTX/DOCX/XLSX を単一 API でカバーし、レイアウト・表構造を明示的に推定するため、pypdf 比の改善が**期待できる**（対象コーパスでの優位は実測まで未確定）。オフライン運用方針とも両立します。
- **多形式を前処理で Markdown 化する方式が、スコープ拡大により構造的に有利。** 全形式を `processed/**/*.md` に正規化すれば、**ingest 側は既存の `.md` TextLoader 経路のみで全形式をカバー**でき、`load_documents` への `.html`/`.pptx` Loader 追加が不要になります。
- **Docling の `HybridChunker` は本システムの既知課題に対応する。** トークナイザ認識分割が「文字数 vs トークン数」の齟齬（日本語で末尾が黙って切り捨てられる問題、[構成要素解説](../06-tuning/README.md) §2）を解消し、`contextualize()` が見出し文脈の付与を担い、`repeat_table_header` が表のチャンク跨ぎ時のヘッダ再掲を行えます（いずれも Docling の構造認識が正しい場合に有効）。**これらは `DoclingDocument` を保持している場合のみ使える**点が方式選択に効きます（§6 の案A/案B）。
- **比較対象を必ず立てて同一条件で測る。** 軽量比較対象に **MarkItDown**（MIT・GPU 不要）、高機能比較対象に **MinerU**（ライセンス条件の確認が前提）。順位づけは実測後に行います。
- **公開ベンチマークは対象言語・文書種・版・指標が異なり、順位を直接比較できない。** 参考指標は **OmniDocBench v1.0**（CVPR 2025）/ **olmOCR-Bench**（英語中心）。最終判断は本件コーパス（日本語白書等）での同一条件実測です。
- **最大の運用留意点:** 重い依存（torch＋モデル）と初回モデルダウンロードを **NAT 開放中の取得フェーズで事前 prefetch** し、パース本体は**取得用 venv に閉じ込める**こと。

---

## 3. 現状整理（文書フローと組込み箇所）

| 工程 | 内容 |
|---|---|
| 取得 | `download_soumu_whitepaper.sh` → `raw/whitepaper/`、`download_ipa.sh` → `raw/ipa/`（いずれも前処理なし）。e-Gov は `preprocess_egov.py` で XML→Markdown、Wikipedia は `preprocess_wikipedia.py` で txt 化 |
| 配置 | `prepare_stage.sh` が whitepaper/ipa は **`RAW_DIR` から**、laws/wikipedia は `PROCESSED_DIR` から `documents/<group>/` へコピー |
| 取り込み | `common.py:load_documents` が `.pdf`（PyPDFLoader）/ `.md` / `.txt`（TextLoader, `autodetect_encoding=True`）を glob。**`.html` / `.pptx` は対象外** |
| 分割 | `split_documents` = `RecursiveCharacterTextSplitter`（`CHUNK_SIZE` 既定 500 / `CHUNK_OVERLAP` 既定 100・日本語セパレータ）。見出し構造は未利用 |
| メタデータ | 案2/3 は `assign_group_metadata` が `documents/<group>/` 第1階層から `group` を導出（ACL 用）。`DOCS_DIR` 外のパスや `documents/` 直下のファイルは **fail closed（SystemExit）で停止**する。**`source` と `group` を壊さないことが統合の必須条件** |

前処理の雛形としては [preprocess_egov.py](scripts/preprocess_egov.py)（`load_env` で `corpus.env` 読込、`--input-dir`/`--output-dir`、mtime 比較でスキップ、出典を先頭に付与）が理想的です。

---

## 4. 多形式変換ツール比較

### 4-1. 候補一覧（同一軸での整理）

普及度（GitHub star 等）は**関心度の指標であり、実運用件数や品質を示さない**ため補助情報とします（2026-07-24 閲覧、概算）。品質欄の記述は公開情報に基づく期待値であり、**本件コーパスでの優劣は §9 の実測まで未確定**です。

| ツール | 入力形式（本件3形式） | ライセンス（コード / モデル重み） | 日本語・縦書き | 表・読み順 | CPU/GPU | オフライン適性 | 補助情報（普及度） |
|---|---|---|---|---|---|---|---|
| **Docling** (IBM) | PDF/HTML/PPTX ○（＋DOCX/XLSX 等） | MIT / モデルも許容的（要版確認） | 高い認識率との報告あり（要実測） | DocLayNet＋TableFormer で明示的に推定 | CPU 可・GPU で高速化 | ◎ ローカル実行・モデル事前取得可 | 約 63.7k star。LangChain/LlamaIndex/Haystack 統合 |
| **MarkItDown** (Microsoft) | PDF/HTML/PPTX ○（＋音声/EPUB/メール等） | MIT | 未検証 | 画像・表の抽出は弱いとの報告 | CPU のみで可（GPU 不要） | ◎ 軽量 | 約 168.6k star、依存公開リポジトリ約 3,079 件（GitHub 概算） |
| **Unstructured** | PDF/HTML/PPTX ○（30+ 形式） | OSS ライブラリ: Apache-2.0（別に商用 API/プラットフォームの提供あり） | 未検証 | 複雑レイアウトで列ずれ等の報告 | CPU 可 | ○（依存が多くデプロイは重め） | RAG 界隈で定番 |
| **Apache Tika** | PDF/HTML/PPTX ○（1000+ 形式） | Apache-2.0 | 抽出自体は堅実 | **構造化 Markdown を出さない**（プレーンテキスト＋メタデータ） | CPU・軽量 | ◎（Java 必要） | Java 圏のデファクト。長期実績 |
| **Marker** (Datalab) | PDF/画像/PPTX/DOCX/XLSX/HTML/EPUB ○ | コード: リポジトリ LICENSE は Apache-2.0（README に GPL 表記が残る不整合あり）/ **モデル重み: modified AI Pubs Open Rail-M** — 研究・個人・資金調達額または売上 2M USD 未満のスタートアップは無償、それ以外の商用利用は別ライセンス。**要法務確認** | 縦書きの公式対応表明なし。日本語単独の再現可能な精度値は現行公式情報で確認できず（要実測） | 表・数式・フォームに強いとの報告 | GPU 推奨 | ○ | olmOCR-Bench 76.1±1.1（Marker 1.10.1、英語中心） |
| **MinerU** (OpenDataLab) | PDF/画像 ○＋現行版は DOCX/PPTX/XLSX も入力対象。HTML は別プロジェクト MinerU-HTML（本体と同一経路かは要確認） | **MinerU Open Source License**（Apache-2.0＋追加条項、2026年4月に旧 AGPL 系から変更）: 商用利用可能だが **MAU 1億超または月間総収益 2,000万 USD 超で別ライセンス**、第三者向けオンラインサービスには **MinerU 利用の表示義務**。**要法務確認** | CJK に強いとの報告（PaddleOCR＋独自レイアウトモデル、109 言語）。縦書き最強との評判は一次情報未確認（要実測） | 数式 LaTeX 化・多段組の読み順復元 | GPU 推奨 | ○ | 中国語圏中心に採用報告多数 |
| **olmOCR** (AllenAI) | PDF/画像のみ | Apache-2.0 | 英語中心（日本語は要実測） | スキャン文書 OCR 特化 | GPU 前提 | ○ | olmOCR-Bench 82.4±1.1（olmOCR v0.4.0） |
| **PyMuPDF4LLM** | PDF のみ | **AGPL-3.0 または別途商用ライセンス（デュアル）**。[構成要素解説](../06-tuning/README.md) §1 も注意喚起済み。**要法務確認** | pypdf より高品質との報告 | Markdown 出力あり | CPU・軽量 | ◎ | — |

### 4-2. 単機能の堅実な選択肢（フォールバック）

- **HTML:** Trafilatura（Apache-2.0、本文抽出の品質に定評）、Pandoc（GPL-2.0、CLI 利用なら実務上の懸念は小さい）
- **PPTX:** python-pptx（MIT）
- **PDF:** pdfminer.six / pypdf / pdfplumber（いずれも MIT 系。構造化 Markdown は出さない）

### 4-3. 評価上の注意

1. **公開評価は対象言語・文書種・版・指標が異なるため、順位を直接比較できません。** olmOCR-Bench は英語中心の OCR ベンチマークで、日本語変換の優劣を示しません。OmniDocBench v1.0（CVPR 2025）は 1,651 PDF ページ／10 文書種／5 レイアウト／5 言語で、28 種の block-level と 4 種の span-level 注釈を含みます。各値を統合した「中立的序列」は存在しないため、**本件の日本語コーパスで同一条件比較**します。
2. **画像として埋め込まれた表の OCR は、どのエンジンでも依然として大きな課題**が残る、という点は各所で共通した見解です。
3. **ライセンスが選定を強く縛ります。** コードとモデル重みでライセンスが異なる場合がある点に注意してください（Marker が典型）。MIT/Apache-2.0（Docling・MarkItDown・Unstructured OSS・Tika・olmOCR）が安全圏、AGPL デュアル（PyMuPDF4LLM）・独自条項（MinerU）・重みに制限（Marker）は**採用前に法務確認**が必要です。本レポートでは除外せず、条件を明記した上で候補に残しています。

---

## 5. Docling の Chunking とフレームワーク連携

Docling は変換だけでなく**チャンカーを標準搭載**しており、これが本システムにとって変換品質と並ぶ価値になります。

### 5-1. HierarchicalChunker

`DoclingDocument` の構造情報から**検出した文書要素ごとに1チャンク**を生成します。リスト項目は既定でマージ（`merge_list_items=True`）、見出し・キャプションをメタデータとして付与します。

### 5-2. HybridChunker

階層チャンキングの上に**トークナイザ認識のリファインメント**を掛ける2パス方式です（①超過したチャンクのみ分割 → ②文脈が一致する小チャンク同士を結合）。

| パラメータ | 役割 |
|---|---|
| `tokenizer` | `BaseTokenizer` 実装を渡す（**モデル名の文字列は不可**）。**埋め込みモデルと揃える** |
| `max_tokens` | チャンクあたりトークン上限。**`HuggingFaceTokenizer` 側に設定**する（`HybridChunker` の引数ではない） |
| `merge_peers` | 小さすぎる隣接チャンクを結合（既定 `True`） |
| `repeat_table_header` | 表がチャンクをまたぐ際にヘッダ行を再掲（既定 `True`） |
| `omit_header_on_overflow` | 上限超過行でヘッダを省き、行の完全性を優先（既定 `False`） |

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

**既知課題への対応**（[構成要素解説](../06-tuning/README.md) §2 と対応）:

- 「**chunk_size は文字数、モデル上限はトークン数**。日本語は 1 文字が 1〜2 トークンに割れ、末尾が黙って切り捨てられる」→ トークナイザ指定で**トークン基準の分割**となり原理的に解消。
- 「**文書タイトル > 章 > 節 をチャンク先頭に付記すると精度が上がる**」→ `contextualize()` は検出済みの見出し・キャプション等を含む**メタデータ強化表現**を返す。正しいタイトル階層になるかは**見出し検出・階層推定の精度に依存**する。
- 現行の `RecursiveCharacterTextSplitter` は表構造を認識しないため、**表内に境界が来るとヘッダと行が分離し得る**。Docling が表構造を正しく認識できた場合、`repeat_table_header` は各分割チャンクへヘッダを再掲できる（誤認識された表を修復する機能ではない）。

### 5-3. LangChain 連携（`langchain-docling`）

`DoclingLoader` のパラメータは `file_path` / `converter` / `convert_kwargs` / `export_type` / `md_export_kwargs` / `chunker` / `meta_extractor`。2モードあり、いずれも `lazy_load()` に対応します。

```python
# DOC_CHUNKS（既定）: 変換とチャンキングを一気通貫
from langchain_docling import DoclingLoader
from langchain_docling.loader import ExportType

loader = DoclingLoader(
    file_path="whitepaper.pdf",
    export_type=ExportType.DOC_CHUNKS,
    chunker=chunker,   # §5-2 で構築した HybridChunker（HuggingFaceTokenizer を保持）
)
docs = loader.load()   # 1 chunk = 1 LangChain Document

# MARKDOWN: 文書まるごと1 Document、分割は自前
loader = DoclingLoader(file_path="whitepaper.pdf", export_type=ExportType.MARKDOWN)
```

**`dl_meta` メタデータ（出典提示の評価軸）:** `doc_items`（`self_ref` / `parent` / `label` / `prov` に **`page_no`・`bbox`・`charspan`**）、`headings`、`origin`（`mimetype` / `binary_hash` / `filename`）。**ページ番号と座標つきの根拠提示**が可能になり、回答の出典表示を「ファイル名」から「何ページのどこ」へ精緻化できます。現行の `source` / `group` と併存させられるかは検証対象です。

### 5-4. LlamaIndex 連携（参考）

`llama-index-readers-docling`（`DoclingReader`）＋ `llama-index-node-parser-docling`（`DoclingNodeParser`）。`export_type="json"` で **DoclingDocument を可逆シリアライズ**、`"markdown"` は非可逆です。本リポジトリは LangChain 系のため直接は使いませんが、**「可逆 JSON で構造を保存できる」という事実が §6 の案B を成立させます**。

---

## 6. チャンキング方式のトレードオフ（案A / 案B — 実測で決定）

**前提となる制約: `HybridChunker` の恩恵は `DoclingDocument` を保持している間しか得られません。** 前処理で Markdown に書き出した時点で構造情報は失われ、`MarkdownHeaderTextSplitter`（見出しのみ）に劣化します。ただし可逆 JSON シリアライズがあるため、両立の道があります。

| 観点 | **案A: `.md` のみ ＋ 見出し分割** | **案B: `.md` ＋ JSON 併出力 ＋ HybridChunker** |
|---|---|---|
| 前処理出力 | `processed/**/*.md` | `processed/**/*.md` と DoclingDocument JSON |
| ingest 側の分割 | `MarkdownHeaderTextSplitter` → `RecursiveCharacterTextSplitter` | JSON から `HybridChunker` |
| ingest 依存追加 | **なし**（既存 `TextLoader` 経路） | `docling-core[chunking]`（transformers・semchunk 等の**推移依存を含む**。パースモデル・torch の直接要求はないが、増分は lock 後に実測） |
| トークン基準分割 | ✕（`from_huggingface_tokenizer` で個別対処は可能） | ◎ 標準機能 |
| 見出し文脈の付与 | △ 手実装が必要 | ◎ `contextualize()`（精度は見出し検出に依存） |
| 表のチャンク跨ぎ | ✕ 表内に境界が来るとヘッダと行が分離し得る | ◎ `repeat_table_header`（表認識が正しい場合） |
| `page_no` / `bbox` 出典 | ✕ 失われる | ◎ `dl_meta` で保持 |
| 成果物容量 | 小（md のみ） | 大（JSON 併存。容量は要計測） |
| スキーマ互換性 | 影響なし | **DoclingDocument schema 更新の影響を受ける**。旧 JSON の読込互換性を版更新時に確認 |
| 変換の追跡・再現 | md に出典を焼き込み | 変換設定・モデル revision・schema 版を JSON 側に記録可能 |
| 再変換コスト | 版更新時は md 再生成のみ | 版更新時に JSON 再生成が必要になる場合あり |
| 失敗時の調査 | md を目視すれば良い | JSON 構造の理解が必要 |
| セキュリティ / ロールバック | 影響小 | 依存増分の SBOM/CVE 確認、旧構成への戻し手順が必要 |

いずれの案も**パース本体（`docling` ＋ torch ＋レイアウト/表モデル）は取得用 venv に閉じたまま**である点は共通です。案B の成立性は、**lock 後のイメージ差分・最大 RSS・CVE・オフライン起動試験**で判定し、**採否はそれらの実測と Hit Rate / MRR 等の比較で決定します**（§9）。

---

## 7. Docling 採用の妥当性・実現性

### 妥当性

- **表・段組み・読み順:** pypdf は表・多段組の論理構造復元を目的としないため読み順が崩れ得ます（[download.md](download.md) §2 の検収でも目視確認を要求）。Docling はレイアウト・読み順・表構造を明示的に推定するため**改善が期待できます**。ただし Docling にも複雑表・見出し階層・縦書きでの失敗はあり、**白書/IPA での現行 PyPDFLoader 比の改善率を実測するまで優位性は未確定**です。
- **多形式の単一 API:** PDF/HTML/PPTX/DOCX/XLSX を `DocumentConverter` 一つで扱え、形式ごとにツールを増やさずに済みます（スコープ拡大に対する最大の利点）。
- **チャンキングまで一貫:** §5 の通り、変換とチャンキングが同じ文書モデル上で完結します。

### 実現性

- 既存 3 前処理スクリプトと同型で追加可能。MIT・Python 3.10+・ローカル実行で、`~=`（マイナー系互換）ピン運用・隔離ネットワーク前提と整合します。
- **OCR は既定で有効（`do_ocr=True`）です。** デジタル PDF では OCR は本来不要のため、性能比較では `PdfPipelineOptions(do_ocr=False)` を明示した系列も測定します。

### OCR / スキャン資料への対応（LLM 利用の可否）

- **Docling の「OCR エンジン」枠に LLM は指定できません。** OCR エンジン抽象が受けるのは Tesseract / EasyOCR / RapidOCR / OcrMac の古典 OCR のみです。
- ただし**別系統の VLM パイプライン**で **OpenAI 互換エンドポイント**を指定できます。これは OCR レイヤの差し替えではなく、**パース全体を VLM に置き換える end-to-end 経路**です。現行の書き方は新ランタイム方式（`VlmConvertOptions.from_preset` ＋ `ApiVlmEngineOptions`）で、`ApiVlmOptions` は legacy 系です:

```python
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import VlmConvertOptions, VlmPipelineOptions
from docling.datamodel.vlm_engine_options import ApiVlmEngineOptions, VlmEngineType
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.pipeline.vlm_pipeline import VlmPipeline

vlm_options = VlmConvertOptions.from_preset(
    "granite_docling",
    engine_options=ApiVlmEngineOptions(
        runtime_type=VlmEngineType.API,
        url="http://llm-001:8000/v1/chat/completions",  # self-hosted vLLM
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

- **本システムでは外部 API 送信を回避し、既に運用中の self-hosted vLLM の OpenAI 互換エンドポイントに向ける**ことで、オフラインを保ったまま VLM パースが可能です。ただし、**vLLM 側が VLM（画像入力対応モデル）を serve する構成、モデル互換性、認証ヘッダの扱いは別途検証**が必要です。ページ画像を 1 枚ずつ推論するため低速・高負荷であり、**通常は既定パイプライン、崩れる資料のみ VLM** という使い分けを推奨します。

### リスク・留意点

| 項目 | 内容 | 対応方針 |
|---|---|---|
| 依存の重さ | torch＋レイアウト/表モデルで数百 MB〜GB 級 | パース本体は**取得用 venv のみ**。ingest コンテナ（`python:3.11-slim`）には入れない（案B でも `docling-core[chunking]` のみ、増分は要実測） |
| オフライン運用 | 初回にモデル自動ダウンロード。NAT は取得時のみ開放 | 取得フェーズでモデルを**事前 prefetch** しキャッシュ固定。[事前準備](prerequisites.md) に手順追記 |
| スループット | 単一ノード処理。数百ページで分単位 | `processed/` に永続化するバッチ前処理のため ingest 毎の再実行にならず許容。mtime スキップで再実行も安価 |
| 抽出の当たり外れ | 資料により品質差 | 現行 PyPDFLoader 出力との**サンプル比較**を検収に組込み、崩れる資料のみ他ツール/VLM に切替える判断余地を残す |
| 依存ピン | `~=` マイナー系互換の運用 | `docling~=<minor>` でピン。torch も CPU 版で明示ピン。API は版依存のため PoC で版固定して動作確認 |
| 案1b | Open WebUI は `ingest.py`/`documents/` を持たない | 生成した Markdown を UI/API 経由でアップロードする運用として明記 |
| 表記正規化 | NFKC/neologdn は分割前に一度だけ（[構成要素解説](../06-tuning/README.md) §2） | Docling 出力直後（前処理段）で正規化する位置づけとする |

---

## 8. なぜ Loader 置換ではなく前処理ステップか

| 観点 | 前処理ステップ（推奨） | ingest 時 Loader 置換 |
|---|---|---|
| 依存の分離 | 重いパース依存を取得用 venv に閉じ込め、独自 ingest を持つ 3 案（案1/2/3。案1b は独自 ingest なし）のイメージを軽量維持 | 3 イメージすべてが肥大化（torch は現状 案1 のみ） |
| 冪等性・再現性 | `processed/` に永続化＋mtime スキップ。フル再構築のたびに変換が走らない | 素朴な実装では再構築のたびに全文書を再変換（変換キャッシュの実装で緩和は可能） |
| 検証の粒度 | 現行 Loader 出力との比較検収を前処理段で実施し、**崩れる資料だけ差し替え**可能 | 資料単位のルーティングを実装すれば可能だが、前処理段より複雑 |
| **多形式対応** | 全形式を `*.md` に正規化 → **ingest は既存 `.md` 経路のみで完結**（`.html`/`.pptx` の Loader 追加が不要） | `load_documents` に形式ごとの Loader/glob 追加が必要 |
| 既存パターン | `preprocess_egov.py` / `preprocess_wikipedia.py` と同型で運用統一 | 既存の前処理規約から外れる |
| オフライン | モデル prefetch を NAT 開放中の取得フェーズに自然に寄せられる | ingest 実行時にモデル取得が必要になりうる |

本リポジトリは**バッチ取得 → 段階配置 → フル再構築**の運用のため、前処理段が構造的に合致します。ただし、**低遅延の増分更新、原本とインデックスの強い一貫性、変換成果物を永続管理したくない要件**が生じた場合は、キャッシュ付き Loader 方式も候補になります。

---

## 9. 検証方法（採用可否の判断根拠）

### 9-1. 評価資料の事前固定

日本語デジタル PDF・スキャン PDF・縦書き・2段組・複雑表を**各 10 ページ以上**、白書/IPA コーパスから事前に選定して固定する（恣意的な事後選定を避ける）。HTML・PPTX のサンプルも同時に固定する。

### 9-2. 測定指標

| 対象 | 指標 |
|---|---|
| 文字抽出 | CER、欠落率、重複率 |
| 読み順 | block pair accuracy |
| 表 | TEDS または cell-level precision/recall |
| 見出し | level 付き precision/recall |
| 出典 | `page_no` 正解率 100%、bbox IoU（閾値を事前設定） |
| RAG | Evidence Recall、MRR、nDCG（質問単位 bootstrap 信頼区間つき） |
| 性能 | pages/s、最大 RSS、成果物サイズ、コンテナイメージ増分 |

### 9-3. 比較系列

- **ベースライン: 現行 `PyPDFLoader` の出力を保存して比較**する（`pdftotext` は Poppler 系の**別**ベースラインとして分離。現行システムの代用にしない）
- Docling（既定パイプライン。`do_ocr=True`/`do_ocr=False` の両系列）
- 軽量比較対象: MarkItDown ／ 高機能比較対象: MinerU（ライセンス確認後）
- チャンキング: pypdf ベースライン・案A・案B の3系列で Hit Rate / MRR 等を比較

### 9-4. 合格条件（例。PoC 開始前に確定する）

- 現行 pypdf 比で主要構造指標（CER・表・読み順）を悪化させないこと
- Evidence Recall を 5 ポイント以上改善すること
- 評価資料内で重大欠落（節単位の本文欠落）0 件

### 9-5. その他の検証

1. **出典提示:** 案B で `dl_meta` の `page_no` / `bbox` がチャンクまで到達するか、**現行の `source` / `group` メタデータと併存できるか**（案2/3 の `assign_group_metadata` の fail-closed 挙動と衝突しないか）を確認。
2. **オフライン再現:** モデル prefetch 済みキャッシュで NAT 閉塞状態でも前処理が完走することを確認（トークナイザの `local_files_only=True` 動作を含む）。
3. **案B の成立性:** lock 後のイメージ差分・最大 RSS・SBOM/CVE・オフライン起動試験。DoclingDocument schema の版互換も確認。
4. **ライセンス確認:** MinerU（追加条項）・Marker（モデル重みの Rail-M、README の GPL 表記との不整合）は採用前に法務確認し、結果を本レポートに追記。

---

## 10. 採用時の統合設計（参考・未実装）

1. **新規 `04-corpus/scripts/preprocess_docs.py`**（[preprocess_egov.py](scripts/preprocess_egov.py) を雛形）
   - `load_env`/`corpus.env` 読込、`--input-dir`/`--output-dir`、mtime スキップ
   - `DocumentConverter().convert(path).document.export_to_markdown()` で PDF/HTML/PPTX を一括 `*.md` 出力。出力直後に `unicodedata.normalize("NFKC", …)`（+ neologdn）。出典（資料名・年度・配布 URL・利用条件）を先頭に付与
   - 案B を採る場合は DoclingDocument JSON も併せて出力（変換設定・モデル revision・schema 版を記録）
2. **`prepare_stage.sh` の source 変更:** whitepaper/ipa を `RAW_DIR` → `PROCESSED_DIR/{whitepaper,ipa}` に切替。HTML/PPT 由来の新グループもここに追加
3. **チャンク分割:** 案A なら `split_documents` を `MarkdownHeaderTextSplitter`（`#/##/###`）→ `RecursiveCharacterTextSplitter`（既存 500/100・日本語セパレータ）の二段に。案B なら JSON から `HybridChunker`。いずれも `source`/`group` を保持。**3案の `load_documents`/`split_documents` は同等だが `common.py` 全体は同一ではない**（案1 は `E5Embeddings`/`build_embeddings` を持ち `assign_group_metadata` なし、案2/3 のみ同一）。案1 と案2/3 へ共通ロジックを個別反映し、案2/3 では `assign_group_metadata` との統合を追加確認する
4. **依存追加:** `docling`（＋CPU 版 torch）を **`04-corpus/scripts/requirements.txt` のみ**に追加。案B では ingest 側に `docling-core[chunking]` を追加（増分実測後）
5. **ドキュメント更新:** [download.md](download.md) §2/§3 の「前処理」節を更新、[README.md](README.md) / [scripts/README.md](scripts/README.md) に前処理ステップ追記、[構成要素解説](../06-tuning/README.md) §1/§2 から本レポートへリンク、[事前準備](prerequisites.md) にモデル prefetch 追記
