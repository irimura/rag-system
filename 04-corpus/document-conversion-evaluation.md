# 文書変換ツール選定 評価レポート（PDF / HTML / PPT → Markdown 前処理）

> 本レポートは**採用可否を判断するための評価**であり、実装は未着手です。前処理スクリプトの追加、`prepare_stage.sh` / `common.py` の改修、依存追加、各ドキュメント更新は、採用決定後の別タスクとします。
>
> 調査時点: 2026年7月。ライセンス条件・ベンチマーク値・API 仕様は変動するため、採用前に一次情報で再確認してください。

## 1. 背景と目的

本リポジトリは vLLM + LangChain ベースの日本語 RAG システムのドキュメント/リファレンス集で、**コーパス取得（フェーズ 04）→ ingest 取り込み（フェーズ 03）**の二段構成です。

現状の PDF コーパス（総務省 情報通信白書・IPA 公開資料）は前処理なしで `raw/` から `documents/{whitepaper,ipa}/` へ配置され、ingest 時に **`PyPDFLoader`（pypdf）でページ単位に直接抽出**しています（[plan2 common.py](../03-deployment/plan2/rag-api/common.py)、plan1/plan3 も同一）。[構成要素解説](../06-tuning/README.md) §1 は「**抽出品質が全ての上限を決める**」と明記し、表・段組み・スキャン PDF で pypdf の抽出が壊れる問題を既に課題として挙げています。

本レポートは、この抽出品質の課題に対する無償利用可能な文書変換ツールを比較評価し、**Docling を第一候補とする前処理ステップ**の妥当性・実現性を判断材料として整理します。

### スコープ

取り込み対象を **PDF / HTML / PPT を同等**に扱う前提とします。ここで重要な制約があります —— **現行 `load_documents` は `.pdf` / `.md` / `.txt` しか glob しておらず、`.html` / `.pptx` の取り込み経路がそもそも存在しません**。

---

## 2. 結論（サマリ）

- **推奨: Docling を第一候補として前処理ステップで採用。** MIT・ローカル実行で PDF/HTML/PPTX/DOCX/XLSX を単一 API でカバーし、表・多段組・読み順を保持した構造化 Markdown を出力します。オフライン運用方針と両立します。
- **多形式を前処理で Markdown 化する方式が、スコープ拡大により決定的に有利。** 全形式を `processed/**/*.md` に正規化すれば、**ingest 側は既存の `.md` TextLoader 経路のみで全形式をカバー**でき、`load_documents` への `.html`/`.pptx` Loader 追加が不要になります（3 つの `common.py` で差分ゼロに近い）。
- **Docling の `HybridChunker` は本システムの既知課題を原理的に解く。** トークナイザ認識分割が「文字数 vs トークン数」の齟齬（日本語で末尾が黙って切り捨てられる問題、[構成要素解説](../06-tuning/README.md) §2）を解消し、`contextualize()` が見出し文脈の焼き込みを自動化、`repeat_table_header` が表のチャンク跨ぎを救います。**ただしこれらは `DoclingDocument` を保持している場合のみ有効**です（§5 の案A/案B）。
- **比較検証の対を必ず立てる。** 下限ベースラインに **MarkItDown**（MIT・最速・GPU 不要）、日本語縦書き/複雑表の上限比較に **MinerU**（ライセンス確認が前提）を置きます。
- **精度の主張はソース間で矛盾しており、ブログの序列を鵜呑みにしない。** 中立指標は **OmniDocBench**（CVPR 2025）/ **olmOCR-Bench**。最終判断は `05-evaluation` の評価セットによる Hit Rate / MRR 実測です。
- **最大の運用留意点:** 重い依存（torch＋モデル）と初回モデルダウンロードを **NAT 開放中の取得フェーズで事前 prefetch** し、パース本体は**取得用 venv に閉じ込める**こと。

---

## 3. 現状整理（文書フローと組込み箇所）

| 工程 | 内容 |
|---|---|
| 取得 | `download_soumu_whitepaper.sh` → `raw/whitepaper/`、`download_ipa.sh` → `raw/ipa/`（いずれも前処理なし）。e-Gov は `preprocess_egov.py` で XML→Markdown、Wikipedia は `preprocess_wikipedia.py` で txt 化 |
| 配置 | `prepare_stage.sh` が whitepaper/ipa は **`RAW_DIR` から**、laws/wikipedia は `PROCESSED_DIR` から `documents/<group>/` へコピー |
| 取り込み | `common.py:load_documents` が `.pdf`（PyPDFLoader）/ `.md` / `.txt`（TextLoader, `autodetect_encoding=True`）を glob。**`.html` / `.pptx` は対象外** |
| 分割 | `split_documents` = `RecursiveCharacterTextSplitter`（`CHUNK_SIZE` 既定 500 / `CHUNK_OVERLAP` 既定 100・日本語セパレータ）。見出し構造は未利用 |
| メタデータ | 案2/3 は `assign_group_metadata` が `documents/<group>/` 第1階層から `group` を導出（ACL 用）。**`source` と `group` を壊さないことが統合の必須条件** |

前処理の雛形としては [preprocess_egov.py](scripts/preprocess_egov.py)（`load_env` で `corpus.env` 読込、`--input-dir`/`--output-dir`、mtime 比較でスキップ、出典を先頭に付与）が理想的です。

---

## 4. 多形式変換ツール比較

### 4-1. PDF / HTML / PPT を単一ツールでカバーできるもの

| ツール | ライセンス | 普及度 | 品質評価 | 本件適合 |
|---|---|---|---|---|
| **Docling** (IBM) | **MIT** | GitHub 約 63.6k star。LangChain / LlamaIndex / Haystack / CrewAI に公式統合 | DocLayNet(レイアウト)＋TableFormer(表構造)。**表・多段組・学術 PDF に強く**、構造保持が最優先の RAG 用途で高評価。日本語も縦書き・複雑レイアウトで高い認識率との報告 | **◎ 第一候補** |
| **MarkItDown** (Microsoft) | **MIT** | **約 139k star（2026年6月時点）**で本カテゴリ最大。2,700+ プロジェクトで採用 | **最速・GPU 不要**（100 ページ 12 秒）。Office 変換は堅実。ただし**画像・表の抽出が弱い**。音声/EPUB/メールなど Docling 非対応形式もカバー | **○ 下限ベースライン** |
| **Unstructured** | Apache-2.0（コア）＋商用 API | RAG 界隈で定番。30+ 形式 | 形式カバレッジ最広・RAG 向けチャンク戦略同梱。**デプロイが最も重く**、複雑レイアウトで列ずれ等の精度低下報告 | △ 重量級 |
| **Apache Tika** | Apache-2.0 | Java 圏のデファクト。長期実績・枯れ具合は随一 | 1000+ 形式を確実に処理。ただし出力は**プレーンテキスト＋メタデータ中心で、構造化 Markdown を出さない** | △ 見出し分割の恩恵なし |
| **Marker** (Datalab) | **商用利用に制限あり（要法務確認）** | 人気は高い | olmOCR-Bench **76.1**。表・数式・フォームに強い。PDF/画像/PPTX/DOCX/XLSX/HTML/EPUB 対応。日本語は Surya 依存で **86.2%**、**縦書きは公式対応表明なし**（要事前検証） | △ ライセンス確認が前提 |

### 4-2. PDF 特化だが品質が高いもの

| ツール | ライセンス | 評価 | 本件適合 |
|---|---|---|---|
| **MinerU** (OpenDataLab / 上海 AI Lab) | **独自「MinerU Open Source License」**（Apache-2.0 ベース＋追加条件。旧 AGPL-3.0 から変更） | **CJK・日本語縦書きに最強**との評価。PaddleOCR＋独自レイアウトモデル、109 言語、数式 LaTeX 化、多段組の読み順復元。**HTML/PPT 非対応** | **○ 日本語の上限比較用** |
| **olmOCR** (AllenAI) | Apache-2.0 | olmOCR-Bench **82.4** で Marker(76.1) を上回る。**スキャン文書 OCR 特化**、PDF/画像のみ | ○ スキャン資料が出た場合 |
| **PyMuPDF4LLM** | **AGPL-3.0** | 軽量・高品質だがライセンスが本用途で要注意（[構成要素解説](../06-tuning/README.md) §1 も注意喚起済み） | △ 法務確認必須 |

### 4-3. 単機能の堅実な選択肢（フォールバック）

- **HTML:** Trafilatura（Apache-2.0、本文抽出の品質に定評）、Pandoc（GPL-2.0、CLI 利用なら実務上の懸念は小さい）
- **PPTX:** python-pptx（MIT）
- **PDF:** pdfminer.six / pypdf / pdfplumber（いずれも MIT 系。構造化 Markdown は出さない）

### 4-4. 評価上の注意

1. **「最高精度」の主張はソース間で矛盾します。** Docling が他を大幅に上回るとする記事と、MinerU が最も高精度とする記事が併存しています。中立的な判断には **OmniDocBench**（CVPR 2025、1,651 PDF ページ／10 文書種／5 レイアウト／5 言語、28 種のブロック注釈）と **olmOCR-Bench** の実測値を参照してください。
2. **画像として埋め込まれた表の OCR は、どのエンジンでも依然として大きな課題**が残る、という点は各所で共通した見解です。
3. **ライセンスが選定を強く縛ります。** MIT/Apache-2.0（Docling・MarkItDown・Unstructured・Tika・olmOCR）が安全圏、AGPL（PyMuPDF4LLM）・独自ライセンス（MinerU）・商用制限（Marker）は**採用前に法務確認**が必要です。本レポートでは除外せず、条件を明記した上で候補に残しています。

---

## 5. Docling の Chunking とフレームワーク連携

Docling は変換だけでなく**チャンカーを標準搭載**しており、これが本システムにとって変換品質と並ぶ価値になります。

### 5-1. HierarchicalChunker

`DoclingDocument` の構造情報から**検出した文書要素ごとに1チャンク**を生成します。リスト項目は既定でマージ（`merge_list_items=True`）、見出し・キャプションをメタデータとして付与します。

### 5-2. HybridChunker

階層チャンキングの上に**トークナイザ認識のリファインメント**を掛ける2パス方式です（①超過したチャンクのみ分割 → ②文脈が一致する小チャンク同士を結合）。

| パラメータ | 役割 |
|---|---|
| `tokenizer` | **埋め込みモデルと揃える**（必須） |
| `max_tokens` | チャンクあたりトークン上限 |
| `merge_peers` | 小さすぎる隣接チャンクを結合（既定 `True`） |
| `repeat_table_header` | 表がチャンクをまたぐ際にヘッダ行を再掲（既定 `True`） |
| `omit_header_on_overflow` | 上限超過行でヘッダを省き、行の完全性を優先 |

```python
from docling.chunking import HybridChunker

chunker = HybridChunker(
    tokenizer="intfloat/multilingual-e5-large",  # 本システムの埋め込みモデルと一致させる
    max_tokens=512,                              # e5 系の上限
    merge_peers=True,
    repeat_table_header=True,
)
chunks = chunker.chunk(docling_document)
for c in chunks:
    text = chunker.contextualize(c)   # 見出し等を焼き込んだ表現を埋め込みへ
```

**既知課題への直接的な回答**（[構成要素解説](../06-tuning/README.md) §2 と対応）:

- 「**chunk_size は文字数、モデル上限はトークン数**。日本語は 1 文字が 1〜2 トークンに割れ、末尾が黙って切り捨てられる」→ `tokenizer` 指定で**トークン基準の分割**となり原理的に解消。
- 「**文書タイトル > 章 > 節 をチャンク先頭に付記すると精度が上がる**」→ `contextualize()` が**自動で実施**。
- `repeat_table_header` は、現行の `RecursiveCharacterTextSplitter` では確実に壊れる「表がチャンク境界をまたぐ」問題に対応。

### 5-3. LangChain 連携（`langchain-docling`）

`DoclingLoader` のパラメータは `file_path` / `converter` / `convert_kwargs` / `export_type` / `md_export_kwargs` / `chunker` / `meta_extractor`。2モードあり、いずれも `lazy_load()` に対応します。

```python
# DOC_CHUNKS（既定）: 変換とチャンキングを一気通貫
from langchain_docling import DoclingLoader
from langchain_docling.loader import ExportType
from docling.chunking import HybridChunker

loader = DoclingLoader(
    file_path="whitepaper.pdf",
    export_type=ExportType.DOC_CHUNKS,
    chunker=HybridChunker(tokenizer="intfloat/multilingual-e5-large", max_tokens=512),
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
| ingest 依存追加 | **なし**（既存 `TextLoader` 経路） | `docling-core` ＋トークナイザ（**パース本体・torch は不要**だが増分は要計測） |
| トークン基準分割 | ✕（`from_huggingface_tokenizer` で個別対処は可能） | **◎ 標準機能** |
| 見出し文脈の焼き込み | △ 手実装が必要 | **◎ `contextualize()` が自動** |
| 表のチャンク跨ぎ | ✕ 壊れる | **◎ `repeat_table_header`** |
| `page_no` / `bbox` 出典 | ✕ 失われる | **◎ `dl_meta` で保持** |
| イメージ肥大リスク | なし | あり（要計測） |

いずれの案も**パース本体（`docling` ＋ torch ＋レイアウト/表モデル）は取得用 venv に閉じたまま**である点は共通です。案B は前処理集約の原則を保ちつつチャンキングの利点を ingest に持ち込む折衷案で、**採否はイメージ増分の実測と Hit Rate / MRR 比較で決定します**（§9）。

---

## 7. Docling 採用の妥当性・実現性

### 妥当性

- **表・段組み・読み順の保持:** 白書/IPA は図表・段組みが多く、pypdf では列崩れ・順序乱れが起きやすい（[download.md](download.md) §2 の検収でも目視確認を要求）。Docling は Markdown テーブル化と読み順復元でここを改善します。
- **多形式の単一 API:** PDF/HTML/PPTX/DOCX/XLSX を `DocumentConverter` 一つで扱え、形式ごとにツールを増やさずに済みます（スコープ拡大に対する最大の利点）。
- **チャンキングまで一貫:** §5 の通り、変換とチャンキングが同じ文書モデル上で完結します。

### 実現性

- 既存 3 前処理スクリプトと同型で追加可能。MIT・Python 3.10+・ローカル実行で、`~=`（マイナー系互換）ピン運用・隔離ネットワーク前提と整合します。
- OCR は白書/IPA がデジタル PDF なら不要（既定 OFF で高速化）。

### OCR / スキャン資料への対応（LLM 利用の可否）

- **Docling の「OCR エンジン」枠に LLM は指定できません。** OCR エンジン抽象が受けるのは Tesseract / EasyOCR / RapidOCR / OcrMac の古典 OCR のみです。
- ただし**別系統の VLM パイプライン**で **OpenAI 互換エンドポイント**を指定できます（`VlmPipelineOptions(enable_remote_services=True)` ＋ `ApiVlmOptions(url, params.model, headers)`）。これは OCR レイヤの差し替えではなく、**パース全体を VLM に置き換える end-to-end 経路**です。
- **本システムでは外部 API 送信を回避し、既に運用中の self-hosted vLLM の OpenAI 互換エンドポイントに向ける**ことで、オフラインを保ったまま VLM-OCR が可能です。ただしページ画像を 1 枚ずつ推論するため低速・高負荷になります。**通常は既定パイプライン、崩れる資料のみ VLM** という使い分けを推奨します。
- 注意: この API 面は版により変化しています（`ApiVlmOptions` → `ApiVlmEngineOptions` へ統合中）。インストールした版のドキュメントで確認し、`~=` でピンしてください。

### リスク・留意点

| 項目 | 内容 | 対応方針 |
|---|---|---|
| 依存の重さ | torch＋レイアウト/表モデルで数百 MB〜GB 級 | パース本体は**取得用 venv のみ**。ingest コンテナ（`python:3.11-slim`）には入れない（案B でも `docling-core` のみ） |
| オフライン運用 | 初回にモデル自動ダウンロード。NAT は取得時のみ開放 | 取得フェーズでモデルを**事前 prefetch** しキャッシュ固定。[事前準備](prerequisites.md) に手順追記 |
| スループット | 単一ノード処理。数百ページで分単位 | `processed/` に永続化するバッチ前処理のため ingest 毎の再実行にならず許容。mtime スキップで再実行も安価 |
| 抽出の当たり外れ | 資料により品質差 | pypdf 出力との**サンプル比較**を検収に組込み、崩れる資料のみ他ツール/VLM に切替える判断余地を残す |
| 依存ピン | `~=` マイナー系互換の運用 | `docling~=<minor>` でピン。torch も CPU 版で明示ピン |
| 案1b | Open WebUI は `ingest.py`/`documents/` を持たない | 生成した Markdown を UI/API 経由でアップロードする運用として明記 |
| 表記正規化 | NFKC/neologdn は分割前に一度だけ（[構成要素解説](../06-tuning/README.md) §2） | Docling 出力直後（前処理段）で正規化する位置づけとする |

---

## 8. なぜ Loader 置換ではなく前処理ステップか

| 観点 | 前処理ステップ（採用） | ingest 時 Loader 置換（不採用） |
|---|---|---|
| 依存の分離 | 重いパース依存を取得用 venv に閉じ込め、3 つの ingest イメージを軽量維持 | 3 イメージすべてが肥大化（torch は現状 案1 のみ） |
| 冪等性・再現性 | `processed/` に永続化＋mtime スキップ。フル再構築のたびに変換が走らない | 再構築のたびに全文書を再変換（VLM 利用時は特に高コスト） |
| 検証の粒度 | pypdf 出力との比較検収を前処理段で実施し、**崩れる資料だけ差し替え**可能 | 一括置換となり資料単位の制御ができない |
| **多形式対応** | 全形式を `*.md` に正規化 → **ingest は既存 `.md` 経路のみで完結**（`.html`/`.pptx` の Loader 追加が不要） | `load_documents` に形式ごとの Loader/glob 追加が必要 |
| 既存パターン | `preprocess_egov.py` / `preprocess_wikipedia.py` と同型で運用統一 | 既存の前処理規約から外れる |
| オフライン | モデル prefetch を NAT 開放中の取得フェーズに自然に寄せられる | ingest 実行時にモデル取得が必要になりうる |

Loader 置換が有利なのは「毎回最新文書を即時取り込む動的パイプライン」ですが、本リポジトリは**バッチ取得 → 段階配置 → フル再構築**の運用のため、前処理段が構造的に合致します。

---

## 9. 検証方法（採用可否の判断根拠）

1. **抽出品質のサンプル比較:** 白書/IPA の代表 PDF で `pdftotext`（現行 pypdf 相当）／Docling／MarkItDown／MinerU の出力を、**表・段組み・見出し・縦書き**の 4 観点で 5〜10 ページ目視比較（[download.md](download.md) の既存検収手順を流用）。
2. **多形式の疎通:** HTML・PPTX のサンプルを Docling で変換し、見出し・表が Markdown として保持されるか確認。
3. **チャンキング案A/案Bの実測比較:**
   - ingest イメージサイズの増分を計測（案B の `docling-core` ＋トークナイザ追加分）
   - 両案でチャンクを生成し、**トークン超過による末尾切り捨ての有無**、**表のチャンク跨ぎ**、**見出し文脈の付与**を確認
   - `05-evaluation` の評価セットで **Hit Rate / MRR** を pypdf ベースライン・案A・案B の3系列で比較
4. **出典提示の検証:** 案B で `dl_meta` の `page_no` / `bbox` がチャンクまで到達するか、**現行の `source` / `group` メタデータと併存できるか**（案2/3 の `assign_group_metadata` と衝突しないか）を確認。回答画面での「何ページのどこ」表示までの実現性を評価。
5. **オフライン再現:** モデル prefetch 済みキャッシュで NAT 閉塞状態でも前処理が完走することを確認。
6. **ライセンス確認:** MinerU（独自ライセンス）・Marker（商用制限）を候補に残す場合、採用前に条件を確認し結果を本レポートに追記。

---

## 10. 採用時の統合設計（参考・未実装）

1. **新規 `04-corpus/scripts/preprocess_docs.py`**（[preprocess_egov.py](scripts/preprocess_egov.py) を雛形）
   - `load_env`/`corpus.env` 読込、`--input-dir`/`--output-dir`、mtime スキップ
   - `DocumentConverter().convert(path).document.export_to_markdown()` で PDF/HTML/PPTX を一括 `*.md` 出力。出力直後に `unicodedata.normalize("NFKC", …)`（+ neologdn）。出典（資料名・年度・配布 URL・利用条件）を先頭に付与
   - 案B を採る場合は DoclingDocument JSON も併せて出力
2. **`prepare_stage.sh` の source 変更:** whitepaper/ipa を `RAW_DIR` → `PROCESSED_DIR/{whitepaper,ipa}` に切替。HTML/PPT 由来の新グループもここに追加
3. **チャンク分割:** 案A なら `common.py:split_documents` を `MarkdownHeaderTextSplitter`（`#/##/###`）→ `RecursiveCharacterTextSplitter`（既存 500/100・日本語セパレータ）の二段に。案B なら JSON から `HybridChunker`。いずれも `source`/`group` を保持。3 つの `common.py` は同一のため一括反映
4. **依存追加:** `docling`（＋CPU 版 torch）を **`04-corpus/scripts/requirements.txt` のみ**に追加。案B では ingest 側に `docling-core` を追加
5. **ドキュメント更新:** [download.md](download.md) §2/§3 の「前処理」節を更新、[README.md](README.md) / [scripts/README.md](scripts/README.md) に前処理ステップ追記、[構成要素解説](../06-tuning/README.md) §1/§2 から本レポートへリンク、[事前準備](prerequisites.md) にモデル prefetch 追記
