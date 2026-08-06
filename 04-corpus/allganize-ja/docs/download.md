# RAG-Evaluation-Dataset-JA PDF 取得手順書

Allganize の日本語 RAG 評価データセットに対応する PDF を、`documents.csv` 記載の公開元 URL から取得します。HTML ページから PDF URL を探索するスクレイピングは行いません。

> 以降のコマンド例中の `${repo_dir}` は、実行前にこのリポジトリの絶対パスへ置き換えてください。

## 前提条件

- Ubuntu 24.04 または同等の Linux 環境
- Git、Python 3.10 以上、`python3-venv`
- Hugging Face および各公開元へ HTTPS 接続できること
- PDF 一式を保存できる空き容量があること
- 各公開元の利用条件に従うこと

Node A を隔離運用している場合は、取得中だけ一時 NAT + IGW を開通し、作業完了後に閉じます。

## 1. CSV の取得

Hugging Face データセットは、変換検証プロジェクトのルートではなく `04-corpus/allganize-ja/dataset/` へ clone します。clone 後は `dataset/.git/` を含む入れ子の Git リポジトリになります。親リポジトリの `.gitignore` は `04-corpus/allganize-ja/dataset/*` を除外するため、Hugging Face の管理ファイルや CSV を親リポジトリへ追加しません。

以前の版から更新した作業ツリーでは、`dataset/.gitkeep` が残っている場合があります。次のコマンドは、`.gitkeep` 以外の項目があれば停止します。`.gitkeep` だけなら削除し、空になった `dataset/` を削除してから clone します。clone 後に `.gitkeep` を復元する必要はありません。

```bash
cd "${repo_dir}"
dataset_dir=${repo_dir}/04-corpus/allganize-ja/dataset
(
set -e
if [ -d "${dataset_dir}" ]; then unexpected_entry=$(find "${dataset_dir}" -mindepth 1 -maxdepth 1 ! -name .gitkeep -print -quit); if [ -n "${unexpected_entry}" ]; then printf '%s\n' "dataset/ が空ではありません: ${unexpected_entry}"; exit 1; fi; if [ -f "${dataset_dir}/.gitkeep" ]; then rm -v "${dataset_dir}/.gitkeep"; fi; rmdir -v "${dataset_dir}"; fi
git clone https://huggingface.co/datasets/allganize/RAG-Evaluation-Dataset-JA "${dataset_dir}"
)
```

`documents.csv`、`rag_evaluation_result.csv`、入れ子の `.git` と、親リポジトリの除外規則を確認します。PDF 本体は clone には含まれません。

```bash
test -f "${dataset_dir}/documents.csv"
test -f "${dataset_dir}/rag_evaluation_result.csv"
test -d "${dataset_dir}/.git"
git -C "${repo_dir}" check-ignore -v "${dataset_dir}/documents.csv"
```

## 2. Python 環境の準備

```bash
cd "${repo_dir}"
python3 -m venv .venv-allganize
.venv-allganize/bin/python -m pip install --upgrade pip
.venv-allganize/bin/python -m pip install -r 04-corpus/allganize-ja/requirements-download.txt
.venv-allganize/bin/python -m pip check
```

`cryptography` は、AES 暗号化された PDF を `pypdf` で読み取るために必要です。依存追加前に作成した既存の仮想環境では、同じ `pip install -r` を再実行してください。

## 3. PDF の一括取得と検証

```bash
cd "${repo_dir}"
.venv-allganize/bin/python 04-corpus/allganize-ja/scripts/download_pdfs.py
```

既定では CSV を `04-corpus/allganize-ja/dataset/` から読み、PDF を `04-corpus/allganize-ja/pdfs/`、結果を `04-corpus/allganize-ja/manifest.csv` に保存します。保存名には `documents.csv` の `file_name` を使い、`rag_evaluation_result.csv` の `target_file_name` と Unicode 正規化後に完全一致することを確認します。評価結果から参照されない `documents.csv` の行は対象外として画面に表示し、逆に評価対象名が `documents.csv` に存在しない場合は入力不整合として停止します。

2026年8月6日時点の Hugging Face main ブランチでは `documents.csv` は65行ですが、`target_file_name` の異なる値は64件です。このため取得対象は評価で参照される64文書となります。データセット更新後は、実行時に表示される「評価対象」の件数を確認してください。

各 HTTP リクエストには User-Agent と 30 秒のタイムアウトを設定し、開始間隔を 1 秒以上空けます。一時的なネットワークエラー、HTTP 429、HTTP 5xx は最大 3 回、1 秒、2 秒の指数バックオフで再試行します。HTTP 4xx や HTML 応答は再試行せず失敗として記録します。

既存 PDF はスキップするため、同じコマンドを再実行できます。既存ファイルも `pypdf` で開き、実ページ数を `documents.csv` の `page` と比較します。ページ数の不一致は標準エラーと manifest に警告として残ります。

`cryptography>=3.1 is required for AES algorithm` と記録された PDF はダウンロード自体には成功しており、ページ数検証だけが失敗しています。上記の依存更新後に同じコマンドを再実行すると、保存済み PDF をスキップしてページ数検証をやり直します。

タイムアウトとリクエスト間隔を変更する例です。

```bash
.venv-allganize/bin/python 04-corpus/allganize-ja/scripts/download_pdfs.py --timeout 60 --interval 1.5
```

保存先を変更する場合は、`${output_dir}` と `${manifest_path}` を実行前に置き換えます。

```bash
output_dir=${repo_dir}/04-corpus/allganize-ja/pdfs
manifest_path=${repo_dir}/04-corpus/allganize-ja/manifest.csv
.venv-allganize/bin/python 04-corpus/allganize-ja/scripts/download_pdfs.py --dataset-dir "${dataset_dir}" --output-dir "${output_dir}" --manifest "${manifest_path}"
```

処理終了時に成功数、失敗数、ページ数不一致数と、失敗文書の一覧を表示します。1 件でも失敗した場合の終了コードは `1`、入力や設定のエラーは `2` です。

## 4. manifest の確認

`manifest.csv` は Excel でも文字化けしにくい UTF-8 BOM 付きで、次の列を持ちます。

| 列 | 内容 |
|---|---|
| `文書名` / `URL` | `documents.csv` の文書名と公開元 URL |
| `成否` | `成功` または `失敗` |
| `HTTPステータス` | 最後に受け取った HTTP ステータス。通信前の失敗や既存ファイルのスキップ時は空欄 |
| `保存パス` / `ファイルサイズ` | PDF の絶対パスとバイト数 |
| `期待ページ数` / `実ページ数` / `ページ数一致` | CSV 記載値との検証結果 |
| `エラー` | リンク切れ、HTML 応答、PDF 解析エラー等の理由 |

```bash
cd "${repo_dir}/04-corpus/allganize-ja"
column -s, -t manifest.csv | less -S
find pdfs -maxdepth 1 -type f -name '*.pdf' | wc -l
```

## 5. 失敗時の手動対応

終了時の「手動入手が必要な文書」または manifest の `成否=失敗` を確認します。リンク切れや URL 変更の場合は、`文書名` と公開元を手掛かりに公開元の公式サイト内で最新版ではなく同じ版の PDF を探してください。自動スクリプトで HTML ページを巡回・解析しないでください。

入手した PDF は manifest の `保存パス` に示された名前で `04-corpus/allganize-ja/pdfs/` へ配置します。別名にすると `target_file_name` と突合できません。配置後に同じ一括取得コマンドを再実行すると、手動配置ファイルをスキップしつつ PDF として開けるか、ページ数が一致するかを再検証し、manifest を更新します。

ページ数だけが不一致の場合は、公開元が差し替えた版、表紙・奥付の有無、ダウンロード不完了を確認します。正しい旧版を入手できない場合は、manifest の該当行を評価記録へ転記し、その文書を評価対象から除外したことと理由を残します。

## 6. サンプル選定へ進む

PDF 取得と manifest の確認が完了したら、変換検証のサンプルを選びます。

```bash
cd "${repo_dir}/04-corpus/allganize-ja"
python3 scripts/select_sample.py
column -s, -t sample_list.csv
```
