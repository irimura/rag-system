# Node A 事前構築手順書

## 0. 位置づけ

本書は **Node A / Node A-2 / Node A-3(vLLM 推論専用の GPU ノード)**を構築・動作確認する共通手順です。システム一式をまとめて構築する場合は [aws-provisioning.md](aws-provisioning.md)(IaC 的な Bash/CLI 手順)を使ってください。本書は GPU ノード部分だけを取り出し、単体構築・単体動作確認をしたい場合の手順です。

- スペックの根拠: [node-specs.md](../01-design/node-specs.md) §1
- ネットワーク設計(プライベートサブネット・EICE 接続): [aws-provisioning.md](aws-provisioning.md) 方針・設計 / §1.1・§1.2・§1.4
- vLLM のサービス化(共通 compose・service): [02-provisioning/node-a/](node-a/)
- ノード別設定: [Node A-2](node-a-2/) / [Node A-3](node-a-3/)

## 1. システム要件

vLLM の確定要件([node-specs.md](../01-design/node-specs.md) §1.1 と同一)。

- CPU: x64
- GPU: NVIDIA **Ampere 世代以降**
- CUDA **12.8 対応**
- VRAM: Node A / A-2 は **40GB 以上**、Node A-3 は **80GB 以上**
- 必須ソフトウェア: NVIDIA Driver / NVIDIA Container Toolkit(Docker で vLLM を動かすため)
- インターネット接続(セットアップ時のみ。イメージ・モデル取得用)

## 2. 推奨インスタンス

| ノード | モデル / 最大シーケンス長 | EC2 インスタンス | GPU / VRAM | ホスト RAM | EBS |
|---|---|---|---|---:|---:|
| Node A | GPTQ 4bit / 32k | **g6e.2xlarge**(最小: g6e.xlarge) | L40S ×1 / 48GB | 64GB(最小 32GB) | gp3 200GB〜 |
| Node A-2 | GPTQ 8bit / 16k | **g6e.2xlarge**(最小: g6e.xlarge) | L40S ×1 / 48GB | 64GB(最小 32GB) | gp3 200GB〜 |
| Node A-3 | 16bit 非量子化 / 32k | **p5.4xlarge** | H100 ×1 / 80GB | 256GB | gp3 300GB〜 |
| Node A-3(代替) | 同上 | g6e.12xlarge | L40S ×4 / 192GB(2 GPU・96GB を使用) | 384GB | gp3 300GB〜 |

Node A-3 の p4de / p5 系と 2×L40S 案の比較、EBS の再計算方法は [node-specs.md §1.3・§4](../01-design/node-specs.md)を正とします。全ノードの OS / AMI は **Ubuntu 24.04**・Deep Learning Base OSS Nvidia Driver GPU AMI です。

> 24.04 を採用する理由: 利用する vLLM の Docker イメージ(`vllm/vllm-openai`)が Ubuntu 24.04 ベースであり、ホスト OS を合わせておくとカーネル/ドライバの組み合わせ検証が揃うため。DLAMI は NVIDIA Driver・Docker・NVIDIA Container Toolkit が導入済みで、[node-specs.md §1.4](../01-design/node-specs.md) の判断根拠どおり個別インストールが不要。

## 3. EC2 インスタンス作成

### 3.1 設定値

| 項目 | 設定値 |
|---|---|
| インスタンスタイプ | g6e.xlarge 〜 g6e.2xlarge |
| AMI | Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 24.04) |
| ストレージ | gp3 200GB〜 |
| ネットワーク | 既存の VPC・プライベートサブネット(新規に一式作る場合は [aws-provisioning.md](aws-provisioning.md) §1.1 を先に実行) |
| パブリック IP | **無効**(割り当てない) |
| Security Group | 内部通信は同一 SG 内許可、22 番は EICE の SG からのみ許可(外部 SSH は開けない。§1.2 参照) |

上表は Node A / A-2 の値です。Node A-3 は §2 のとおり gp3 300GB 以上から開始し、16bit モデルの実ファイルサイズの 2〜3 倍へ再計算します。

### 3.2 起動(CLI)

VPC・サブネット・SG が [aws-provisioning.md](aws-provisioning.md) §1.1・§1.2 で作成済みである前提(`${vpc_id}` `${subnet_id}` `${sg_id}` は同書の変数を再利用)。

```bash
dlami_owner=amazon
dlami_name='Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 24.04)*'
dlami=$(aws ec2 describe-images --owners ${dlami_owner} --filters "Name=name,Values=${dlami_name}" "Name=state,Values=available" --query 'sort_by(Images,&CreationDate)[-1].ImageId' --output text)
target_hostname=llm-001
ip_llm=192.168.0.10

cat > user-data-${target_hostname}.sh <<EOF
#!/bin/bash
hostnamectl set-hostname ${target_hostname}
EOF

llm_id=$(aws ec2 run-instances \
  --image-id "${dlami}" \
  --instance-type "g6e.2xlarge" \
  --key-name "${key_name}" \
  --subnet-id "${subnet_id}" \
  --security-group-ids "${sg_id}" \
  --private-ip-address "${ip_llm}" \
  --no-associate-public-ip-address \
  --block-device-mappings "DeviceName=/dev/sda1,Ebs={VolumeSize=200,VolumeType=gp3}" \
  --metadata-options "HttpTokens=required" \
  --user-data "file://user-data-${target_hostname}.sh" \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Project,Value=${project}},{Key=Name,Value=${target_hostname}}]" \
  --query 'Instances[0].InstanceId' --output text)
aws ec2 wait instance-running --instance-ids ${llm_id}
rm -v user-data-${target_hostname}.sh
```

### 3.3 接続(EICE)

パブリック IP を持たないため、[aws-provisioning.md §1.4](aws-provisioning.md) の EC2 Instance Connect Endpoint(EICE)経由で接続する。

```bash
aws ec2-instance-connect open-tunnel --instance-id ${llm_id} --local-port 5222 &
ssh -i ${key_name}.pem -p 5222 ubuntu@localhost
```

## 4. 事前導入済みソフトウェアの確認

DLAMI には NVIDIA Driver・Docker・NVIDIA Container Toolkit が導入済みのため、インストール作業は不要。動作確認のみ行う。

```bash
nvidia-smi                # GPU 認識・ドライバの CUDA Version(12.8 以上)を確認
docker --version
docker compose version
nvidia-ctk --version
```

期待結果例(`nvidia-smi`):

```text
+-----------------------------------------------------------------------------+
| NVIDIA-SMI 570.xxx.xx      Driver Version: 570.xxx.xx   CUDA Version: 12.8  |
| GPU  Name        Persistence-M | Memory-Usage                              |
|   0  NVIDIA L40S             On |    0MiB / 49140MiB                       |
+-----------------------------------------------------------------------------+
```

ノード別に期待する GPU メモリは次のとおりです。`nvidia-smi` の表示単位・予約領域により、カタログ値と表示値には差があります。

| ノード / 案 | 期待する GPU 数 | カタログ VRAM | `nvidia-smi` の目安 |
|---|---:|---:|---|
| Node A / A-2(L40S) | 1 | 48GB | 約 45,000MiB 以上 |
| Node A-3(H100 / A100 80GB) | 1(8 GPU 固定インスタンスでは搭載数 8) | 80GB/GPU | 約 80,000MiB 以上/GPU |
| Node A-3(2×L40S) | 搭載 4、vLLM 使用 2 | 48GB/GPU | 約 45,000MiB 以上/GPU |

GPU を使った Docker コンテナの動作確認:

```bash
docker run --rm --gpus all nvidia/cuda:12.8.0-runtime-ubuntu24.04 nvidia-smi
```

正常に GPU 情報が表示されれば、コンテナから GPU が利用できる状態。ここまでで §5(任意の手動導入)は不要。

## 5. (任意)DLAMI を使わない場合の手動導入

素の Ubuntu 24.04 AMI から構築する場合のみ実施する。DLAMI 使用時はスキップ。

### 5.1 OS 更新

```bash
sudo apt update
sudo apt upgrade -y
sudo reboot
```

再接続する(§3.3)。以降、ドライバ互換性維持のためセキュリティパッチ以外のカーネル更新は避ける([node-specs.md](../01-design/node-specs.md) §1.4)。

### 5.2 NVIDIA Driver インストール

```bash
sudo apt install -y ubuntu-drivers-common
sudo ubuntu-drivers install
sudo reboot
```

再接続後、`nvidia-smi` で CUDA Version が 12.8 以上であることを確認する(§4)。

### 5.3 Docker インストール

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg lsb-release

sudo mkdir -pv /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

cat <<EOF | sudo tee /etc/apt/sources.list.d/docker.list
deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable
EOF

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker ${USER}   # 再ログインで反映

docker --version
docker compose version
```

### 5.4 NVIDIA Container Toolkit インストール

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt update
sudo apt install -y nvidia-container-toolkit

sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

導入後は §4 の GPU コンテナ動作確認で仕上げる。

## 6. vLLM の起動(共通ファイルとノード別 .env を使用)

独自の compose を組む必要はなく、リポジトリ同梱の [02-provisioning/node-a/docker-compose.yml](node-a/docker-compose.yml)を全 GPU ノードで共通利用します(vLLM 自体に同梱の OpenAI 互換サーバ `vllm serve` を Docker 公式イメージ `vllm/vllm-openai` 経由で起動する構成。自前の API ラッパーは不要)。

| ノード | 作業ディレクトリ | `MAX_MODEL_LEN` | `TENSOR_PARALLEL_SIZE` |
|---|---|---:|---:|
| Node A | `node-a/` | 8192(初期値。モデル要件の最大は 32768) | 1 |
| Node A-2 | `node-a-2/` | 16384 | 1 |
| Node A-3(単一 GPU) | `node-a-3/` | 32768 | 1 |
| Node A-3(2×L40S) | `node-a-3/` | 32768 | 2 |

`GPU_MEMORY_UTILIZATION=0.90`は全ノード共通です。以下は Node A の例で、A-2 / A-3 は各 README の `--env-file` / `-f` 指定を使います。

```bash
git clone ${repo_url}
cd rag-system/02-provisioning/node-a

cp -v .env.example .env
vim .env   # MODELS_DIR / MODEL_PATH / SERVED_MODEL_NAME / VLLM_API_KEY を設定

docker compose up -d
docker compose logs -f vllm   # "Application startup complete" が出るまで待つ(モデルロードに数分)
```

状態・動作確認(`${vllm_api_key}` は `.env` に設定した `VLLM_API_KEY` の値に置き換える):

```bash
docker compose ps
curl http://localhost:8080/v1/models -H "Authorization: Bearer ${vllm_api_key}"
```

GPU 利用状況の監視(別ターミナル):

```bash
watch -n 1 nvidia-smi
```

停止:

```bash
docker compose down
```

## 7. 運用上の注意

- **利用しない時間帯は EC2 を停止する**。手動停止のほか、[aws-provisioning.md §1.5](aws-provisioning.md) の EventBridge Scheduler で毎日 18:00 に自動停止できる
- **モデル格納用に十分な EBS 容量を確保する**(gp3 200GB〜。サイジングの考え方は [node-specs.md](../01-design/node-specs.md) §4)
- **Security Group は最小限のみ開放する**。外部への SSH は開けず EICE 経由に統一し、vLLM API(8080)は Node B の SG からのみ許可する([node-specs.md](../01-design/node-specs.md) §5)
- **インターネット接続はセットアップ時のみ**。Docker イメージ取得・モデルダウンロードにはインスタンス自身の外向き通信が必要なため、その間だけ [aws-provisioning.md §2](aws-provisioning.md) の NAT Gateway を一時作成し、完了後は削除する(定常運用は隔離)
- GPU 利用状況(使用率・VRAM 消費量)は `nvidia-smi` で定期的に監視する
