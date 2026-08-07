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
export DOCLING_VLLM_URL=http://127.0.0.1:8080/v1/chat/completions
read -rsp 'vLLM model name: ' DOCLING_VLLM_MODEL; printf '\n'; export DOCLING_VLLM_MODEL
read -rsp 'vLLM API key: ' DOCLING_VLLM_API_KEY; printf '\n'; export DOCLING_VLLM_API_KEY
```

APIへ接続できることだけを確認します。応答本文は表示しません。

```bash
curl --fail --silent --show-error -o /dev/null -H @- http://127.0.0.1:8080/v1/models \
  <<< "Authorization: Bearer ${DOCLING_VLLM_API_KEY}"
```

`-H @-` は認証ヘッダーを標準入力から渡します。APIキーはcurlのコマンドライン引数へ含まれません。

次に、64×64ピクセルのテスト画像を1回送信し、画像入力に対応していることを確認します。この確認では推論が1回発生します。スクリプトが表示するのは `画像入力確認: OK` またはモデル名を含まない失敗理由だけです。モデル名、APIキー、応答本文は表示しません。

```bash
.venv-docling-vlm-commercial/bin/python scripts/check_docling_vlm_commercial_api.py
```

この試験はAPIが画像を受理できることだけを確認します。PDF変換の品質やMarkdownの再現性は、後続のサンプル変換で評価してください。

Docker Composeで稼働するvLLMコンテナのホストPIDを計測対象として設定します。GPUを直接使うワーカーPIDではなく、コンテナの最上位PIDを指定することで、APIサーバーとその子孫ワーカーを計測します。

```bash
vllm_compose_dir=/home/ubuntu/rag-system/02-provisioning/node-a
vllm_container_id="$(docker compose \
  --project-directory "${vllm_compose_dir}" \
  -f "${vllm_compose_dir}/docker-compose.yml" \
  ps -q vllm)"
test -n "${vllm_container_id}"
export DOCLING_VLLM_PID="$(docker inspect --format '{{.State.Pid}}' "${vllm_container_id}")"
test "${DOCLING_VLLM_PID}" -gt 0
ps -p "${DOCLING_VLLM_PID}" -o pid=,ppid=,comm=
```

Composeファイルを別のディレクトリから起動した場合は、`vllm_compose_dir`を実際のプロジェクトディレクトリへ変更してください。`docker inspect`の `.State.Pid` は、コンテナPID 1に対応するホストPIDです。`nvidia-smi`に表示されるエンジンワーカーPIDは指定しません。

このコマンドはComposeのサービス名が `vllm` であることを前提とします。`02-provisioning/node-a/docker-compose.yml` のサービス名を変更する場合は、本手順も同時に変更してください。

必要に応じて、モデル名を含まないプロンプトファイルと実行設定を指定します。

```bash
export DOCLING_VLLM_TIMEOUT=300
export DOCLING_VLLM_MAX_TOKENS=8192
export DOCLING_VLLM_CONCURRENCY=4
export DOCLING_VLLM_SCALE=2.0
export CONVERT_TIMEOUT=21600
```

`CONVERT_TIMEOUT` はPDF 1件全体の制限秒数です。既定値は7200秒です。数百ページのPDFでは、費用を伴う処理が完了直前に打ち切られないよう、ページ数と事前実測に基づいて増やしてください。

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

current_vllm_container_id="$(docker compose \
  --project-directory "${vllm_compose_dir}" \
  -f "${vllm_compose_dir}/docker-compose.yml" \
  ps -q vllm)"
current_vllm_pid="$(docker inspect --format '{{.State.Pid}}' "${current_vllm_container_id}")"
test "${current_vllm_pid}" = "${DOCLING_VLLM_PID}"
```

最後の `test` が失敗した場合は、変換中にコンテナが再起動した可能性があります。その実行のRAMとVRAMは過少計測の可能性があるため、比較値として採用せず再計測してください。

比較結果には、実モデル名ではなく `commercial-vlm-a` などの内部承認済み別名、モデル版、量子化、vLLM版、プロンプト版、ウォームアップ有無を記録します。実モデル名との対応は、アクセス制御された別の台帳で管理してください。

## トラブルシューティング

- `DOCLING_VLLM_*を設定してください` と表示された場合は、値を表示せず同じシェルで再設定します。
- HTTP 401または403の場合は、APIキーとvLLMの認証設定を確認します。APIキーをログへ貼り付けません。
- 画像入力に関するHTTP 400の場合は、モデルとvLLMがOpenAI互換の画像入力に対応しているか確認します。
- 事前確認が `FAILED` になった場合は、HTTPステータスとvLLM側のアクセス制御済みログを確認します。応答本文は共用ログや障害票へ貼り付けません。
- Markdownが空または説明文だけの場合は、プロンプトとモデルの文書変換能力を確認します。実モデル名は障害票へ記載しません。
- タイムアウト時は `DOCLING_VLLM_TIMEOUT` を増やします。出力が途中で切れる場合は `DOCLING_VLLM_MAX_TOKENS` とvLLM側のコンテキスト長を確認します。
- PDF全体が7200秒で打ち切られる場合は、ページ数とサンプル実測から `CONVERT_TIMEOUT` を見積もり直します。
- `DOCLING_VLLM_PID` の確認に失敗した場合は、実際に起動に使ったComposeプロジェクトで `docker compose ps vllm` を実行し、コンテナの状態と `vllm_compose_dir` を確認します。
- vLLMのリクエストログにモデル名や本文を残さないでください。導入済みvLLMの `vllm serve --help` で `--disable-log-requests` の対応を確認し、非公開モデルの管理者が起動設定へ反映します。サービス設定やログの内容を共用ログへ貼り付けません。

変換アダプター自身が生成する例外は、モデル名とAPIキーを伏せ字にしてからメトリクスへ渡します。DoclingとvLLMを含む外部ライブラリのログ管理とアクセス制御は別途必要です。
