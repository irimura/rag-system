# MinerU pipeline変換手順書

## 概要

**警告:** 現行配布物はAGPL-3.0です。改変物の配布やネットワークサービス提供を含む利用条件を法務担当者が確認するまで、内部検証に限定してください。

レイアウト、OCR、表、数式を組み合わせるパイプラインのバックエンドを使います。1文書ずつ実行します。

## 前提条件

Node A（Ubuntu 24.04、Python 3.11以上、NVIDIA L4 24 GB、RAM 16 GB）で実行します。シェル変数を使うコマンドは、実行前に値を確認してください。

```bash
cd 04-corpus/allganize-ja
nvidia-smi
python3 --version
df -h .
```

`sample_list.csv`、`pdfs/`、共通依存の `pypdf` が必要です。モデル取得中だけ外部接続を許可し、取得後は版とライセンスを記録します。

## インストール

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-dev build-essential poppler-utils
python3 -m venv .venv-mineru
source .venv-mineru/bin/activate
python -m pip install --upgrade pip
python -m pip install 'mineru[pipeline]>=3,<4' pypdf psutil 'six==1.17.0' 'cryptography==49.0.0'
mineru-models-download
python -m pip freeze > metrics/mineru-versions.txt
```

GPUを使うプロダクトでは、次が `True` になることを確認します。PyTorchを使わない製品では製品固有の確認コマンドを優先します。

```bash
python -c 'import torch; print(torch.cuda.is_available(), torch.version.cuda)' || true
```

## サンプル変換の実行

### 一時API方式

```bash
source .venv-mineru/bin/activate
.venv-mineru/bin/python scripts/convert_mineru.py
```

出力は `out/mineru/<元ファイル名>.md`、メトリクスは `metrics/mineru.csv` です。既存の空でないMarkdownはスキップします。

この方式はPDFごとに一時的な `mineru-api` を起動します。PDFごとにパイプラインモデルを初期化する版では、初期化時間も各文書の変換所要時間に含まれます。

### 常駐API方式（推奨）

常駐API方式では、MinerU APIを1回起動し、各PDFの変換要求を同じAPIへ送ります。既存のRAG用vLLMは使用しません。API起動中はパイプラインモデルがGPUメモリを使用するため、ほかのGPUプロセスを停止しておきます。

APIをバックグラウンドで起動し、共通計測処理がAPI側のRAMとVRAMを観測できるようPIDを保存します。

```bash
cd /home/ubuntu/rag-system/04-corpus/allganize-ja
source .venv-mineru/bin/activate
nohup .venv-mineru/bin/mineru-api --host 127.0.0.1 --port 8000 > metrics/mineru-api.log 2>&1 &
mineru_api_pid=$!
cat > /tmp/allganize-mineru-api.pid <<EOF
${mineru_api_pid}
EOF
```

起動ログと疎通を確認します。

```bash
cd /home/ubuntu/rag-system/04-corpus/allganize-ja
tail -n 20 metrics/mineru-api.log
curl --fail --silent --show-error http://127.0.0.1:8000/openapi.json >/dev/null
```

パイプラインモデルは最初の変換要求で初期化されます。初期化時間を本計測から除く場合は、代表PDFを1件変換してウォームアップします。

```bash
warmup_pdf=$(find pdfs -maxdepth 1 -type f -name '*.pdf' | sort | head -1)
mkdir -pv out/mineru-api-warmup
.venv-mineru/bin/mineru -p "${warmup_pdf}" -o out/mineru-api-warmup -b pipeline --api-url http://127.0.0.1:8000
```

ウォームアップ完了後、常駐API用スクリプトでサンプルを変換します。

```bash
.venv-mineru/bin/python scripts/convert_mineru_api.py
```

APIのURLを変更した場合は、実行前に環境変数を設定します。

```bash
export MINERU_API_URL=http://127.0.0.1:8000
.venv-mineru/bin/python scripts/convert_mineru_api.py
```

出力とメトリクスは一時API方式と共通で、それぞれ `out/mineru/` と `metrics/mineru.csv` に保存します。常駐API用スクリプトはPIDファイルを読み、変換クライアントとAPIプロセス系統のRAM・VRAMを合算して観測します。同じ結果へ異なる方式を混在させず、比較結果に「一時API」または「常駐API（ウォームアップ有無）」を記録します。

## 全件実行

比較手順書の選定基準を満たした場合だけ実行します。

```bash
source .venv-mineru/bin/activate
.venv-mineru/bin/python scripts/convert_mineru.py --all
```

常駐API方式で全件を変換する場合は、APIの起動と疎通確認を済ませてから実行します。

```bash
.venv-mineru/bin/python scripts/convert_mineru_api.py --all
```

失敗原因を直して再変換する場合だけ `--force` を追加します。RAM 16 GBのため並列実行しません。大きいPDFでOOMが起きた場合は一時ディレクトリでページ分割し、順番に変換してから結合します。分割条件を結果へ記録します。

## メトリクス確認

```bash
column -s, -t metrics/mineru.csv | less -S
python scripts/aggregate_metrics.py
```

`success=false`、空出力、VRAM 24 GB超過のおそれ、RAM不足を優先して調べます。RAMとVRAMは、変換プロセスとその子孫だけを0.5秒間隔で観測した近似値です。

## トラブルシューティング

- モデル取得コマンドがない版では公式READMEに従います。
- CUDA OOM時はGPU上の別プロセスを停止し、ページ分割を試します。
- 出力が深い階層でもラッパーがMarkdownを正規名へ複製します。
- 常駐API用スクリプトが接続エラーで停止した場合は、API側のSSHセッションと `curl http://127.0.0.1:8000/openapi.json` の結果を確認します。
- 常駐API方式の最初の文書だけ遅い場合は、API側の `model init cost` を確認し、パイプラインモデルの初期化時間が含まれていないか調べます。

常駐APIを停止する場合は、保存したPIDを指定します。停止後にPIDファイルを削除し、GPUメモリが解放されたことを確認します。

```bash
mineru_api_pid=$(cat /tmp/allganize-mineru-api.pid)
kill "${mineru_api_pid}"
for attempt in {1..30}; do if ! kill -0 "${mineru_api_pid}" 2>/dev/null; then break; fi; sleep 1; done
if kill -0 "${mineru_api_pid}" 2>/dev/null; then printf '%s\n' "mineru-apiが30秒以内に停止しませんでした: PID ${mineru_api_pid}" >&2; else rm -fv /tmp/allganize-mineru-api.pid; fi
tail -n 20 metrics/mineru-api.log
nvidia-smi
```

CLIが導入版と異なる場合は、既定値を直接編集せず、まず `.venv-mineru/bin/python scripts/convert_mineru.py --command '{input} を含むコマンド'` で1件を試します。動作確認後に版と変更理由を文書へ反映します。
