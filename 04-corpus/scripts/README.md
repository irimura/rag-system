# コーパス取得・前処理スクリプト

Node B(Ubuntu 24.04)上で、[テストデータ集](../corpus-datasets.md) §1 の推奨コーパスを取得・前処理し、案1/2/3の `documents/<グループ名>/` へ累積配置するスクリプトです。案1bはファイル配置型の ingest を持たないため、後続の `04-corpus/ingest-plan1b.md` に記載する UI/API 手順を使用します。

> 以降のコマンド例中の `${repo_dir}` は、実行前にリポジトリの絶対パスへ置き換えてください。

このディレクトリのスクリプトは外部サイトへ接続します。AWSの隔離運用では、一時 NAT + IGW を開通している取得期間だけ実行し、取得・イメージ準備完了後に閉じます。

## 1. スクリプト一覧

| ファイル | 役割 |
|---|---|
| `corpus.env.example` | 保存先、対象年度、法令 ID、Wikipedia ダンプ条件等の設定例 |
| `common.sh` | `corpus.env` 読み込み、ディレクトリ作成、冪等ダウンロードの共通処理 |
| `download_egov_laws.sh` | e-Gov 法令 API から既定10法令を XML 取得 |
| `preprocess_egov.py` | 法令 XML を条・項見出し付き Markdown に変換 |
| `download_soumu_whitepaper.sh` | 情報通信白書1年度分の PDF を取得。URL未設定時は手動取得へ誘導 |
| `download_ipa.sh` | IPA 情報セキュリティ白書・中小企業向けガイドライン等を取得 |
| `download_livedoor.sh` | livedoor ニュースコーパスを原文のまま取得・展開 |
| `download_wikipedia_dump.sh` | jawiki pages-articles を全件または先頭分割ファイルで取得 |
| `preprocess_wikipedia.py` | WikiExtractorを呼び出し、記事数・カテゴリを任意指定してテキスト化 |
| `prepare_stage.sh` | 段階別セットを案1/2/3の固定グループへコピーまたはシンボリックリンク配置 |

## 2. 依存パッケージ

```bash
sudo apt update
sudo apt install -y curl python3 python3-venv tar
cd ${repo_dir}
python3 -m venv .venv-corpus
source .venv-corpus/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r 04-corpus/scripts/requirements.txt
```

`requirements.txt` は PyPI 公開版の `wikiextractor==3.0.6` に固定しています。WikiExtractor 本体のライセンスは AGPL-3.0-or-laterです。コーパス成果物のライセンスは各配布元の条件に従います。

## 3. `corpus.env` の準備

```bash
cd ${repo_dir}/04-corpus/scripts
cp -v corpus.env.example corpus.env
vim corpus.env
```

| 設定 | 内容 | 既定 |
|---|---|---|
| `CORPUS_DIR` | raw/processedを置くリポジトリ外ディレクトリ | `${HOME}/rag-corpus` |
| `EGOV_LAW_IDS` | 空白区切りの法令ID | 個人情報保護法・労働基準法を含む10法令 |
| `WHITEPAPER_YEAR` | 情報通信白書の対象年度 | `2025` |
| `SOUMU_WHITEPAPER_URL` | 対象年度の PDF 直リンク | 空(公式ページで手動確認) |
| `IPA_PDF_URLS` | IPA PDF の直リンクを空白区切りで指定 | 白書2025 + 中小企業向けガイドライン第4.0版 |
| `WIKIPEDIA_DUMP_DATE` | `latest` または `YYYYMMDD` | `latest` |
| `WIKIPEDIA_MODE` | `full` または `partial` | `partial` |
| `WIKIPEDIA_MAX_ARTICLES` | 前処理する記事数上限。`0` は無制限 | `10000` |
| `WIKIPEDIA_CATEGORIES` | カンマ区切りのカテゴリ完全一致 | 空 |
| `WIKIEXTRACTOR_PROCESSES` | WikiExtractorの並列プロセス数 | `4` |

法令IDの既定値は、個人情報保護法、労働基準法、民法、会社法、著作権法、不正競争防止法、行政手続法、労働契約法、行政機関情報公開法、サイバーセキュリティ基本法です。

## 4. 実行順

### 4.1 動作確認段階

```bash
cd ${repo_dir}
bash 04-corpus/scripts/download_egov_laws.sh
python3 04-corpus/scripts/preprocess_egov.py
bash 04-corpus/scripts/download_soumu_whitepaper.sh
bash 04-corpus/scripts/prepare_stage.sh smoke 2 copy
```

`SOUMU_WHITEPAPER_URL` が空の場合は、表示された公式ページから PDF を手動取得して、表示された保存先へ配置します。

### 4.2 精度評価段階

```bash
cd ${repo_dir}
bash 04-corpus/scripts/download_ipa.sh
bash 04-corpus/scripts/download_livedoor.sh
bash 04-corpus/scripts/prepare_stage.sh accuracy 2 copy
```

動作確認段階の `laws` / `whitepaper` は残したまま、`ipa` / `livedoor` を加えます。livedoor本文は改変・要約保存せず、社内評価用途に限定し、検索内部で生成されるチャンクを含む成果物を再配布しません。

### 4.3 負荷・規模試験段階

```bash
cd ${repo_dir}
bash 04-corpus/scripts/download_wikipedia_dump.sh --mode partial
python3 04-corpus/scripts/preprocess_wikipedia.py --max-articles 10000
bash 04-corpus/scripts/prepare_stage.sh load 2 copy
```

全件ダンプを使う場合は `--mode full` と `--max-articles 0` を指定します。カテゴリだけを対象にする場合は `--category` を複数回指定できます。

```bash
python3 04-corpus/scripts/preprocess_wikipedia.py --max-articles 50000 --category 情報技術 --category コンピュータ
```

Wikipediaの抽出テキストには記事名、元URL、CC BY-SA 4.0を記録します。

## 5. 案と配置方式の切り替え

`prepare_stage.sh` の第2引数は `1` / `2` / `3`、第3引数は `copy` / `symlink` です。既定はコピーです。`SOURCE.md` / `LICENSE.txt` / `CHANGES.txt` / `README.txt` は出典・ライセンス確認用として raw側に保持しますが、検索コーパスには配置しません。

```bash
bash 04-corpus/scripts/prepare_stage.sh accuracy 1 copy
bash 04-corpus/scripts/prepare_stage.sh accuracy 2 copy
bash 04-corpus/scripts/prepare_stage.sh load 3 copy
```

配置先のグループ名は `laws` / `whitepaper` / `ipa` / `livedoor` / `wikipedia` に固定します。`documents/` 直下には配置しません。各段階で既存ファイルを削除せず累積配置し、その後に対象案の ingest を実行してコレクション/インデックスを全量再構築します。

`symlink` はディスク節約用の任意オプションです。`${CORPUS_DIR}` への絶対リンクを作成するため、Docker ingestで使用するには対象案の ingestサービスへ `${CORPUS_DIR}:${CORPUS_DIR}:ro` を追加マウントし、ホストとコンテナで同じ絶対パスを見せる必要があります。具体的な環境変数の読み込みと compose設定は [事前準備](../prerequisites.md) §1を参照してください。標準 compose のまま実行する場合は `copy` を使用してください。
