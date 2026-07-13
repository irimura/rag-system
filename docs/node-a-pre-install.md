# Node A 事前構築手順書

## 1. 概要

本手順では、vLLM 推論サンプルを実行するための AWS EC2 環境を構築する。

### システム要件

- CPU: x64
- GPU: NVIDIA Ampere世代以降
- CUDA 12.8対応
- VRAM 40GB以上
- インターネット接続

### 推奨インスタンス

| 項目 | 内容 |
|--------|--------|
| EC2インスタンス | g6e.xlarge |
| GPU | NVIDIA L40S |
| GPUメモリ | 48GB |
| vCPU | 4 |
| メモリ | 32GB |
| OS | Ubuntu 22.04 |

## 2. 構成

動作確認済みのソフトウェア構成は以下のとおり。

| 種別 | 名称 | バージョン |
|--------|--------|--------|
| OS | Ubuntu | 22.04 |
| ドライバー | NVIDIA Driver | 570.195.03 |
| ミドルウェア | Docker | 28.5.0 |
| ツール | Docker Compose v2 | 2.5.0 |
| ツール | NVIDIA Container Toolkit | 1.18.0 |

## 3. EC2 インスタンス作成

### EC2設定

| 項目 | 設定値 |
|--------|--------|
| インスタンスタイプ | g6e.xlarge |
| AMI | Ubuntu Server 22.04 LTS |
| ストレージ | 200GB以上推奨 |
| セキュリティグループ | SSH(22)許可 |
| パブリックIP | 有効 |

### 接続

```bash
ssh -i <key.pem> ubuntu@<public-ip>
```

## 4. OS更新

```bash
sudo apt update
sudo apt upgrade -y
sudo reboot
```

再接続する。

## 5. NVIDIA Driverの確認

GPU認識確認。

```bash
nvidia-smi
```

期待結果例

```text
+-----------------------------------------------------------------------------+
| NVIDIA-SMI 570.195.03                                                     |
| GPU Name        Memory-Usage                                               |
| NVIDIA L40S     0MiB / 49140MiB                                           |
+-----------------------------------------------------------------------------+
```

## 6. Dockerインストール

### Dockerリポジトリ追加

```bash
sudo apt-get update &&
sudo apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

sudo mkdir -pv /etc/apt/keyrings

curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

cat <<__EOF__> /etc/apt/sources.list.d/docker.list
deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
__EOF__
```

### Dockerインストール

```bash
sudo apt update &&
sudo apt install -y \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin
```

### バージョン確認

```bash
docker --version
docker compose version
```

## 7. NVIDIA Container Toolkit インストール

### リポジトリ登録

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
| sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
| sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
| sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
```

### インストール

```bash
sudo apt update &&
sudo apt install -y nvidia-container-toolkit
```

### Docker設定

```bash
sudo nvidia-ctk runtime configure --runtime=docker

sudo systemctl restart docker
```

## 8. Docker GPU動作確認

```bash
docker run --rm \
    --gpus all \
    nvidia/cuda:12.8.0-runtime-ubuntu22.04 \
    nvidia-smi
```

正常に GPU 情報が表示されれば成功。

## 9. 作業ディレクトリ作成

```bash
mkdir -p ~/vllm
cd ~/vllm
```

---

## 10. Docker Compose準備

プロジェクト構成例

```text
vllm/
├── docker-compose.yml
├── models/
├── output/
└── logs/
```

ディレクトリ作成

```bash
mkdir models output logs
```

## 11. コンテナ起動

Docker Composeファイルに従って起動。

```bash
docker compose up -d
```

状態確認。

```bash
docker compose ps
```

ログ確認。

```bash
docker compose logs -f
```

## 12. GPU利用状況確認

別端末で確認。

```bash
watch -n 1 nvidia-smi
```

GPU使用率およびVRAM消費量を監視する。

## 13. コンテナ停止

```bash
docker compose down
```

## 14. 運用上の注意

- 利用しない時は EC2 を停止する
- モデル格納用に十分な EBS 容量を確保する
- Security Group は最小限のポートのみ開放する
- Docker イメージ取得時およびモデルダウンロード時はインターネット接続が必要
- GPU利用状況は定期的に監視する

