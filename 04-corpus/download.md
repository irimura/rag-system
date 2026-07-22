# コーパスのダウンロードと前処理

> 以降のコマンド例中の `${repo_dir}` は、実行前にリポジトリの絶対パスへ置き換えてください。その他の変数の設定コマンドは各節にあります。先に [事前準備](prerequisites.md) を完了し、`04-corpus/scripts/corpus.env` を作成してください。

取得物は `${CORPUS_DIR}/raw/`、前処理済み成果物は `${CORPUS_DIR}/processed/` に保存します。既存の非空ファイルはスキップするため、同じ設定で再実行できます。

前処理・検収コマンドを実行するシェルでは、最初に共通設定を読み込みます。取得スクリプトは `corpus.env` を自身で読み込むため、この読み込みは不要です。

```bash
cd ${repo_dir}
set -a && source 04-corpus/scripts/corpus.env && set +a
```

## 1. e-Gov法令

### 取得

```bash
bash 04-corpus/scripts/download_egov_laws.sh
```

既定は個人情報保護法、労働基準法を含む10法令です。対象は `corpus.env` の `EGOV_LAW_IDS` で差し替えます。

### 前処理

```bash
python3 04-corpus/scripts/preprocess_egov.py
```

`processed/laws/<法令ID>.md` に法令名、法令番号、法令ID、出典、章・節・条・項を出力します。条見出しは `### 第一条` 等を保持し、TC01/TC03の条番号検索で一致箇所を確認できる構造にします。

### 検収

```bash
find ${CORPUS_DIR}/raw/egov -type f -name '*.xml' | wc -l
find ${CORPUS_DIR}/processed/laws -type f -name '*.md' | wc -l
rg -n '^### 第(一|二|三)条' ${CORPUS_DIR}/processed/laws
```

既定設定では XML/Markdownが各10件で、個人情報保護法と労働基準法の条番号見出しが検索できることを確認します。

## 2. 総務省 情報通信白書

### 取得

`corpus.env` の `WHITEPAPER_YEAR` と `SOUMU_WHITEPAPER_URL` を公式ページで確認してから実行します。

```bash
bash 04-corpus/scripts/download_soumu_whitepaper.sh
```

年度ごとに URL/分冊構成が変わります。`SOUMU_WHITEPAPER_URL` が空の場合、スクリプトは設定が必要な項目を表示して終了します。

### 前処理

案1/2/3の現行 Loader は `PyPDFLoader` で PDF を直接読み込むため、通常は形式変換しません。OCRが必要なスキャン PDF や段組み崩れがある場合は、[構成要素解説](../06-tuning/README.md) §1 に従って別 Loader/OCR の採用を検討し、原本を残したまま検証用出力を分けます。

### 検収

```bash
pdf_file="${CORPUS_DIR}/raw/whitepaper/${SOUMU_WHITEPAPER_FILENAME:-information-communications-whitepaper-${WHITEPAPER_YEAR}.pdf}"
pdfinfo ${pdf_file}
pdftotext -f 1 -l 5 ${pdf_file} - | sed -n '1,120p'
du -h ${pdf_file}
```

冒頭、本文中盤、図表が多い章、末尾から合計5〜10ページを目視し、文字化け、縦書き順序、段組み混線、表の列崩れを記録します。発行元、年度、資料名、配布URLも作業記録へ残します。

## 3. IPA公開資料

### 取得

```bash
bash 04-corpus/scripts/download_ipa.sh
```

既定URLは情報セキュリティ白書2025全章版と中小企業の情報セキュリティ対策ガイドライン第4.0版です。別年度/資料は `IPA_PDF_URLS` と `IPA_SOURCE_PAGE_URLS` を同時に更新します。

### 前処理

現行 Loader では PDF を直接投入します。本文抽出が崩れる資料だけを識別し、Loader/OCR変更の比較対象にします。原 PDF を上書きしません。

### 検収

```bash
find ${CORPUS_DIR}/raw/ipa -type f -name '*.pdf' -print
find ${CORPUS_DIR}/raw/ipa -type f -name '*.pdf' -exec du -h {} \;
pdf_file="$(find ${CORPUS_DIR}/raw/ipa -type f -name '*.pdf' -print | sort | head -n 1)"
pdftotext -f 1 -l 3 ${pdf_file} - | sed -n '1,120p'
```

資料ごとに `pdf_file` を再設定して `pdftotext` を繰り返します。各 PDF で表紙、目次、本文、表/図、付録をサンプリングし、出典情報を確認します。

## 4. livedoorニュースコーパス

### 取得

```bash
bash 04-corpus/scripts/download_livedoor.sh
```

スクリプトは CC BY-ND 2.1 JPの改変禁止・社内評価限定を実行時に表示し、`ldcc-20140209.tar.gz` を取得して原文のまま展開します。

### 前処理

スクリプトが展開したカテゴリ別 `LICENSE.txt` は raw側に保持しますが、`prepare_stage.sh` は `LICENSE.txt` / `CHANGES.txt` / `README.txt` を検索コーパスへ配置しません。本文の書き換え、正規化結果の保存、要約保存は行いません。展開済み `.txt` をそのまま `documents/livedoor/` へ配置し、チャンク分割は ingest コンテナ内部だけで行います。原文、チャンク、Vector DB、派生成果物を再配布しません。

### 検収

```bash
find ${CORPUS_DIR}/raw/livedoor/text -type f -name '*.txt' ! -name 'LICENSE.txt' | wc -l
find ${CORPUS_DIR}/raw/livedoor/text -type f -name 'LICENSE.txt' -print
du -sh ${CORPUS_DIR}/raw/livedoor/text
```

記事件数が7,367件で、9カテゴリの `LICENSE.txt` が存在し、記事本文を変換していないことを確認します。

## 5. Wikipedia日本語版

### 取得

先頭分割ファイルだけを取得する例です。

```bash
bash 04-corpus/scripts/download_wikipedia_dump.sh --mode partial
```

全件は `--mode full` を指定します。`WIKIPEDIA_DUMP_DATE=latest` は実行時点の最新版を指すため、再現性が必要な評価では `YYYYMMDD` を固定します。

### 前処理

```bash
python3 04-corpus/scripts/preprocess_wikipedia.py --max-articles 10000
```

カテゴリを完全一致で絞り込む場合は `--category` を複数指定します。

```bash
python3 04-corpus/scripts/preprocess_wikipedia.py --max-articles 50000 --category 情報技術 --category コンピュータ
```

全件は `--max-articles 0` です。出力済み記事IDはスキップします。抽出条件を変えて厳密に別集合を作る場合は、別の `--output-dir` を指定して混在を避けます。

### 検収

```bash
find ${CORPUS_DIR}/processed/wikipedia -type f -name '*.txt' | wc -l
du -sh ${CORPUS_DIR}/raw/wikipedia ${CORPUS_DIR}/processed/wikipedia
sample_article="$(find ${CORPUS_DIR}/processed/wikipedia -type f -name '*.txt' -print | shuf -n 1)"
sed -n '1,40p' ${sample_article}
```

上のコマンドは出力済みファイルから無作為に1件を選びます。再実行を繰り返して20件以上について、記事名、元URL、CC BY-SA 4.0、本文が入り、テンプレート断片や文字化けが許容範囲かを確認します。

## 6. 配置前の総合検収

```bash
find ${CORPUS_DIR}/raw -maxdepth 3 -type f | sort
find ${CORPUS_DIR}/processed -maxdepth 3 -type f | sort
du -sh ${CORPUS_DIR}/raw/* ${CORPUS_DIR}/processed/*
```

段階ごとの必須グループが揃ったら、対象案の取り込み手順へ進みます。
