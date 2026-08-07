# Docling商用VLM変換手順書

## 概要

**警告:** 非公開モデルの契約、入力PDFの取扱条件、生成物の利用条件、追加費用を確認できるまで実行しないでください。本手順は当初の無償プロダクト比較とは別枠です。

`docling-vlm-commercial` は、Node A上のOpenAI互換vLLMへPDFのページ画像を送り、Markdownを生成します。実モデル名とAPIキーは環境変数だけで設定します。スクリプト、手順書、メトリクスには保存しません。

## 前提条件

Node A（Ubuntu 24.04、g6e.2xlarge、NVIDIA L40S 48 GB、8 vCPU、RAM 64 GiB）で実行します。vLLMのモデルは画像入力とOpenAI互換の `/v1/chat/completions` に対応し、Markdownだけを応答できる必要があります。

次を確認してください。実モデル名とAPIキーの値は画面へ表示しません。

```bash
cd /home/ubuntu/rag-system/04-corpus/allganize-ja
nvidia-smi
.venv-docling-vlm-commercial/bin/python --version
```

`sample_list.csv`、`pdfs/`、稼働中のvLLMが必要です。vLLMの起動と停止には、非公開モデルを管理している既存手順を使ってください。本手順はvLLMを自動で起動または停止しません。

## インストール

既存のDocling VLMとは別のvenvへ導入します。

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-dev build-essential poppler-utils
python3 -m venv .venv-docling-vlm-commercial
source .venv-docling-vlm-commercial/bin/activate
python -m pip install --upgrade pip
python -m pip install 'docling[vlm]==2.*' pypdf psutil
python -m pip check
python -m pip freeze > metrics/docling-vlm-commercial-versions.txt
```

## サンプル変換の実行

APIの接続情報を設定します。モデル名とAPIキーはシェル履歴へ残さないよう、対話入力します。

```bash
export DOCLING_VLLM_URL=http://127.0.0.1:8000/v1/chat/completions
read -rsp 'vLLM model name: ' DOCLING_VLLM_MODEL; printf '\n'; export DOCLING_VLLM_MODEL
read -rsp 'vLLM API key: ' DOCLING_VLLM_API_KEY; printf '\n'; export DOCLING_VLLM_API_KEY
```

APIへ接続できることだけを確認します。応答本文は表示しません。

```bash
curl --fail --silent --show-error -o /dev/null -H "Authorization: Bearer ${DOCLING_VLLM_API_KEY}" http://127.0.0.1:8000/v1/models
```

次に、32×32ピクセルのテスト画像を1回送信し、画像入力に対応していることを確認します。この確認では推論が1回発生します。スクリプトが表示するのは `画像入力確認: OK` またはモデル名を含まない失敗理由だけです。モデル名、APIキー、応答本文は表示しません。

```bash
.venv-docling-vlm-commercial/bin/python scripts/check_docling_vlm_commercial_api.py
```

この試験はAPIが画像を受理できることだけを確認します。PDF変換の品質やMarkdownの再現性は、後続のサンプル変換で評価してください。

GPUを使うプロセスがvLLMの1件だけであることを確認し、そのPIDを計測対象として設定します。複数のPIDが表示された場合は自動選択せず、vLLMのPIDを確認して設定してください。

```bash
mapfile -t gpu_pids < <(nvidia-smi --query-compute-apps=pid --format=csv,noheader,nounits)
if [ "${#gpu_pids[@]}" -eq 1 ]; then export DOCLING_VLLM_PID="${gpu_pids[0]}"; else unset DOCLING_VLLM_PID; printf '%s\n' 'GPUプロセスが1件ではありません。vLLMのPIDを手動で設定してください。' >&2; fi
test -n "${DOCLING_VLLM_PID:-}"
ps -p "${DOCLING_VLLM_PID}" -o pid=,comm=
```

必要に応じて、モデル名を含まないプロンプトファイルと実行設定を指定します。

```bash
export DOCLING_VLLM_TIMEOUT=300
export DOCLING_VLLM_MAX_TOKENS=8192
export DOCLING_VLLM_CONCURRENCY=4
export DOCLING_VLLM_SCALE=2.0
```

サンプルを変換します。

```bash
source .venv-docling-vlm-commercial/bin/activate
.venv-docling-vlm-commercial/bin/python scripts/convert_docling_vlm_commercial.py
```

出力は `out/docling-vlm-commercial/<元ファイル名>.md`、メトリクスは `metrics/docling-vlm-commercial.csv` です。メトリクスのRAMとVRAMには、変換クライアントと指定したvLLMプロセス系統を含みます。

## 全件実行

契約条件と比較手順書の選定基準を満たした場合だけ実行します。特定domainの全件を `sample_list.csv` に設定している場合は、`--all` を付けません。

```bash
source .venv-docling-vlm-commercial/bin/activate
.venv-docling-vlm-commercial/bin/python scripts/convert_docling_vlm_commercial.py --all
```

既存結果を同じ設定で再変換する場合だけ `--force` を追加します。実行後もvLLMをRAGで使う場合は停止しません。検証専用に起動した場合は、既存の非公開モデル管理手順で停止し、`nvidia-smi` でGPUメモリの解放を確認します。

## メトリクス確認

```bash
column -s, -t metrics/docling-vlm-commercial.csv | less -S
python scripts/aggregate_metrics.py
```

比較結果には、実モデル名ではなく `commercial-vlm-a` などの内部承認済み別名、モデル版、量子化、vLLM版、プロンプト版、ウォームアップ有無を記録します。実モデル名との対応は、アクセス制御された別の台帳で管理してください。

## トラブルシューティング

- `DOCLING_VLLM_*を設定してください` と表示された場合は、値を表示せず同じシェルで再設定します。
- HTTP 401または403の場合は、APIキーとvLLMの認証設定を確認します。APIキーをログへ貼り付けません。
- 画像入力に関するHTTP 400の場合は、モデルとvLLMがOpenAI互換の画像入力に対応しているか確認します。
- 事前確認が `FAILED` になった場合は、HTTPステータスとvLLM側のアクセス制御済みログを確認します。応答本文は共用ログや障害票へ貼り付けません。
- Markdownが空または説明文だけの場合は、プロンプトとモデルの文書変換能力を確認します。実モデル名は障害票へ記載しません。
- タイムアウト時は `DOCLING_VLLM_TIMEOUT` を増やします。出力が途中で切れる場合は `DOCLING_VLLM_MAX_TOKENS` とvLLM側のコンテキスト長を確認します。
- `DOCLING_VLLM_PID` の確認に失敗した場合は、`nvidia-smi` でvLLMのホストPIDを確認します。

変換アダプター自身が生成する例外は、モデル名とAPIキーを伏せ字にしてからメトリクスへ渡します。DoclingとvLLMを含む外部ライブラリのログ管理とアクセス制御は別途必要です。
