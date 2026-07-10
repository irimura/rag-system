# Node A: vLLM を OpenAI 互換エンドポイントとしてサービス化する

## 結論 — 自前実装は不要

vLLM 本体に **OpenAI 互換 API サーバが同梱**されています(`vllm serve` コマンド。実体は `vllm.entrypoints.openai.api_server`)。`/v1/chat/completions`・`/v1/completions`・`/v1/models` 等を実装済みで、これが vLLM をサービス化する際の標準 OSS 実装です。**自前の Python スクリプト(FastAPI ラッパー等)を書く必要はなく、書くべきでもありません**(ストリーミング・バッチング・エラー処理・API 互換性の維持をすべて自作で追うことになるため)。

構築ファイルは [deploy/node-a/](../deploy/node-a/) に配置しています。

| 方式 | ファイル | 向くケース |
|---|---|---|
| **Docker Compose(推奨)** | [docker-compose.yml](../deploy/node-a/docker-compose.yml) + [.env](../deploy/node-a/.env.example) | CUDA/PyTorch のバージョン組み合わせを公式イメージに任せられる。Node B と運用手順が揃う |
| venv + systemd | [vllm.service](../deploy/node-a/vllm.service) | ホストに Python 環境を直接構築したい場合。GPU ドライバのみ合わせればよい |

どちらも同じ `vllm serve` を起動しているだけなので、後から方式を切り替えても Node B 側には影響しません(エンドポイント URL とモデル名が同じであればよい)。

> 以降のコマンド例中の `${node_a}` `${node_b_ip}` `${vllm_api_key}` `${served_model_name}` は、実行前に環境に応じた値に置き換えてください。

## 0. 前提: GPU 要求スペック

利用する vLLM の確定要件(詳細とインスタンス選定は [node-specs.md](node-specs.md) §1):

- GPU: **Ampere 世代以降(Compute Capability 8.0+)・VRAM 40GB 以上**
- NVIDIA Driver: **CUDA 12.8 対応版(570 系以降)** — `nvidia-smi` の CUDA Version 表示が 12.8 以上であること
- **NVIDIA Container Toolkit**(§1 の Docker 方式で必須。§2 の venv + systemd 方式では不要)

## 1. Docker Compose 方式(推奨)

### 1.1 前提: NVIDIA Container Toolkit

> AWS EC2 で **Deep Learning Base OSS Nvidia Driver GPU AMI** を使う場合([node-specs.md](node-specs.md))、ドライバ・Docker・NVIDIA Container Toolkit は導入済みのため本節はスキップして §1.2 へ進む。

```bash
# NVIDIA ドライバ導入済みであること(nvidia-smi が動くこと)を確認してから:
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt update && sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# 確認
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

### 1.2 起動

```bash
cd deploy/node-a
cp -v .env.example .env
vim .env   # MODELS_DIR / MODEL_PATH / SERVED_MODEL_NAME / VLLM_API_KEY を設定

docker compose up -d
docker compose logs -f vllm   # "Application startup complete" が出るまで待つ(モデルロードに数分)
```

## 2. venv + systemd 方式

```bash
# vllm ユーザーと環境の準備
sudo useradd -r -m -d /opt/vllm vllm
sudo -u vllm python3 -m venv /opt/vllm/.venv
sudo -u vllm /opt/vllm/.venv/bin/pip install vllm   # CUDA 対応 wheel が入る

# ユニットファイルを配置して ExecStart 内の <> を書き換え
sudo cp -v deploy/node-a/vllm.service /etc/systemd/system/
sudo vim /etc/systemd/system/vllm.service
sudo systemctl daemon-reload
sudo systemctl enable --now vllm
journalctl -u vllm -f
```

## 3. 動作確認

```bash
# モデル一覧(${served_model_name} が返ること)
curl http://${node_a}:8080/v1/models \
  -H "Authorization: Bearer ${vllm_api_key}"

# チャット補完
curl http://${node_a}:8080/v1/chat/completions \
  -H "Authorization: Bearer ${vllm_api_key}" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"${served_model_name}\",\"messages\":[{\"role\":\"user\",\"content\":\"こんにちは\"}]}"
```

Node B 側は各案の `.env` で以下を一致させます。

| Node B(.env) | Node A の設定 |
|---|---|
| `VLLM_BASE_URL=http://${node_a}:8080/v1` | ポート公開(Docker 版は 8080→8000 をマップ済み) |
| `VLLM_MODEL` | `SERVED_MODEL_NAME` |
| `VLLM_API_KEY` | `VLLM_API_KEY`(`--api-key`) |

## 4. 主要オプション(チューニング)

| オプション | 既定値(本構成) | 説明 |
|---|---|---|
| `--served-model-name` | - | API 上のモデル名。モデルのパス名と切り離せるため必ず指定する |
| `--gpu-memory-utilization` | 0.90 | VRAM 確保割合。KV キャッシュもここに含まれる |
| `--max-model-len` | 8192 | 最大コンテキスト長。**OOM 時にまず下げる**。RAG はプロンプトが長くなるため 8k 以上を推奨 |
| `--tensor-parallel-size` | 1 | GPU 複数枚でモデルを分割(40GB に載らないモデルを 2 枚で等) |
| `--api-key` | 必須運用 | Bearer 認証。Node B と共有する |
| `--dtype` / `--quantization` | 自動 | VRAM が厳しい場合に `--quantization awq` 等(量子化済みモデルが必要) |

## 5. セキュリティ

- `--api-key` を必ず設定する(未設定だと LAN 内の誰でも GPU を使える)
- ファイアウォールで 8080/tcp を **Node B からのみ許可**する:

```bash
sudo ufw allow from ${node_b_ip} to any port 8080 proto tcp
sudo ufw deny 8080/tcp
```

## 6. トラブルシューティング

| 症状 | 対処 |
|---|---|
| 起動時 CUDA out of memory | `--max-model-len` を下げる → `--gpu-memory-utilization` を 0.85 に下げる → 量子化モデルを検討 |
| `model not found` | `MODEL_PATH` が HF 形式ディレクトリ(config.json 等がある階層)を指しているか確認 |
| 起動が遅い / タイムアウト | モデルロードには数分かかる。systemd 版は `TimeoutStartSec=600` を設定済み |
| Node B から 401 | `VLLM_API_KEY` の不一致。両ノードの `.env` を確認 |
| Docker で GPU が見えない | §1.1 の toolkit 設定と `docker info | grep -i nvidia` を確認 |
