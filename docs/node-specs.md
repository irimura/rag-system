# ノードスペック選定(AWS EC2)

本設計は特定クラウドのマネージドサービスを使わない構成のため、EC2 は「素の Ubuntu VM」として利用します(オンプレミスに置き換える場合も本書の CPU/RAM/GPU 要件がそのまま基準になります)。

> **ノード名の対応に注意**: 本リポジトリでは一貫して **Node A = GPU ノード(vLLM、VRAM 40GB+、NVIDIA Container Toolkit 必要)/ Node B = アプリ+データノード(GPU 不要)** と定義しています。GPU 要件・GPU AMI が付くのは **Node A** 側です。

## サマリ

| ノード | 役割 | Instance Type(推奨) | AMI |
|---|---|---|---|
| **Node A** | vLLM(推論専用) | **g6e.2xlarge**(最小: g6e.xlarge) | Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 24.04) |
| **Node B** | WebUI / RAG API / 検索 DB / TEI | 案毎に下表(例: 案2 は m7i.xlarge〜) | Ubuntu Server 24.04 LTS(Canonical 公式) |

---

## 1. Node A(GPU ノード)の選定

### 1.1 要求スペック(確定要件)

利用する vLLM の要件として以下が確定しています。

| 項目 | 要件 |
|---|---|
| GPU 世代 | **Ampere 世代以降**(Compute Capability 8.0 以上。A100 / A10 / L4 / L40S / H100 等が該当) |
| VRAM | **40GB 以上** |
| CUDA | **12.8 対応**(NVIDIA Driver は 570 系以降) |
| 必須ソフトウェア | **NVIDIA Driver** / **NVIDIA Container Toolkit**(Docker 方式で vLLM を動かすため) |

- ソフトウェア要件は後述の Deep Learning Base OSS Nvidia Driver GPU AMI で充足できる(§1.4)。導入済みドライバが CUDA 12.8 に対応しているかは、AMI のリリースノートと起動後の `nvidia-smi`(右上の CUDA Version 表示が 12.8 以上)で確認する
- venv + systemd 方式([deploy/node-a/vllm.service](../deploy/node-a/vllm.service))を採る場合、NVIDIA Container Toolkit は不要(Driver のみ必須)

### 1.2 選定基準

GPU インスタンスの選定は、次の順で絞り込みます。

1. **GPU 世代と VRAM が決定打**(vCPU/RAM は二の次)。Ampere 以降かつ VRAM 40GB 以上を**単一 GPU** で満たせるファミリーを選ぶ。複数 GPU の合算でも `--tensor-parallel-size` で動くが、通信オーバーヘッドと運用の複雑さが増すため、載るなら 1 枚に載せるのが基本
2. **ホスト RAM はモデルサイズ以上**を確保する(モデルロード時に読み込むため。VRAM 40GB を使い切るモデルならホスト RAM 64GB が安全)
3. vCPU はトークナイズ・前処理程度なので 4〜8 で足りる
4. 推論はネットワーク負荷が小さいので帯域は既定で十分

### 1.3 候補の比較(2026-07 時点)

| Instance Type | GPU(世代) | VRAM | vCPU / RAM | 判定 |
|---|---|---|---|---|
| **g6e.xlarge** | L40S ×1(Ada Lovelace = Ampere より後) | **48GB** | 4 / 32GB | ○ 最小構成(コスト優先) |
| **g6e.2xlarge** | L40S ×1(同上) | **48GB** | 8 / 64GB | **◎ 推奨**(ホスト RAM に余裕) |
| g5.xlarge | A10G ×1(Ampere) | 24GB | - | × 世代は満たすが VRAM 不足 |
| g6.xlarge | L4 ×1(Ada Lovelace) | 24GB | - | × VRAM 不足 |
| g6e.12xlarge | L40S ×4 | 192GB | 48 / 384GB | △ 70B 級 bf16 等、1 枚に載らない場合のみ(`--tensor-parallel-size 4`) |
| p4d / p5 系 | A100(Ampere)/ H100(Hopper)×8 | 320GB〜 | - | × 要件は満たすが 8 GPU 固定で本用途にはオーバースペック |

- **g6e ファミリー(NVIDIA L40S 48GB/GPU、Ada Lovelace 世代)が「Ampere 以降 + 単一 GPU で 40GB+」を満たす最も経済的な選択肢**です。L40S は CUDA 12.8 対応です。同じ 1 GPU なら xlarge / 2xlarge / 4xlarge の VRAM は同じ 48GB で、差は vCPU / ホスト RAM のみ
- g6e.xlarge(ホスト RAM 32GB)は、VRAM 40GB を使い切るサイズのモデルをロードする際にホスト RAM が窮屈になり得るため、**g6e.2xlarge を推奨**とします。まず xlarge で始めて、ロード時のメモリ不足やスワップが出たら 2xlarge に上げる進め方でも問題ありません
- 月額の試算は §5 を参照。料金は変動するため、確定時に [EC2 オンデマンド料金表](https://aws.amazon.com/ec2/pricing/on-demand/) で対象リージョンの単価を確認してください。検証フェーズは停止(EBS のみ課金)をこまめに行うとコストを抑えられます

### 1.4 AMI

**Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 24.04)** — G6e をサポート対象に含みます。§1.1 の必須ソフトウェア(NVIDIA Driver・**Docker・NVIDIA Container Toolkit**)が導入済みのため、Toolkit の個別導入は不要で、[deploy/node-a/](../deploy/node-a/) の `docker compose up -d` から直接始められます。最新版 AMI のドライバが CUDA 12.8 に対応していることをリリースノートで確認して選択してください。

- 「Base」が付かない DLAMI(PyTorch 入り等)はフレームワーク同梱で大きいだけなので不要。vLLM はコンテナ(または venv)で導入するため Base で十分
- カーネルの自動更新はドライバ互換性を壊すことがあるため、AMI のガイダンスに従いセキュリティパッチ以外のカーネル更新は避ける

## 2. Node B(アプリ+データノード)の選定

### 2.1 選定基準

1. **RAM が決定打**(採用する案の常駐サービス数で決まる): 案1 8GB〜 / 案2 16GB〜 / 案3 32GB〜
2. **vCPU は TEI(embedding/rerank の CPU 推論)が主な消費者**。対話のレイテンシと取り込みバッチの速度に効くため 4 vCPU 以上を推奨
3. GPU は不要(GPU AMI も不要)。取り込みが遅い場合の GPU 追加は後から検討([plan2 参照](plan2-standard.md))
4. バーストが許容できる検証用途なら t3/t4g 系、常用なら非バーストの m/r 系

### 2.2 案毎の推奨

| 案 | 最小(検証) | 推奨(常用) | 備考 |
|---|---|---|---|
| 案1 | t3.large(2vCPU/8GB)<br>常時 約 12,700 円 / 160h 約 2,800 円 | m7i.xlarge(4vCPU/16GB)<br>常時 約 30,400 円 / 160h 約 6,700 円 | embedding/rerank がプロセス内 CPU 実行のため vCPU 多めが快適 |
| 案2 | m7i.xlarge(4vCPU/16GB)<br>常時 約 30,400 円 / 160h 約 6,700 円 | m7i.2xlarge(8vCPU/32GB)<br>常時 約 60,800 円 / 160h 約 13,300 円 | TEI ×2 + Qdrant + WebUI |
| 案3 | r7i.xlarge(4vCPU/32GB)<br>常時 約 37,300 円 / 160h 約 8,200 円 | **r7i.2xlarge(8vCPU/64GB)**<br>常時 約 74,600 円 / 160h 約 16,300 円 | OpenSearch の JVM ヒープ(`OS_HEAP`)+ヒープ外メモリでメモリ優先型(r 系)が適する |

> 月額は §5 と同一根拠(東京リージョン・Linux オンデマンド・1USD=160JPY、常時稼働 730h / 日中帯 160h)。EC2 インスタンス費のみで EBS 等は別途。

- m7i/r7i(Intel)は例示です。同世代の AMD(m7a/r7a)は同スペックでやや安価なので、リージョンの提供状況と単価で選んで構いません
- **ARM(Graviton, m7g/r7g)は避けてください**。本構成のコンテナイメージ(TEI CPU 版等)は x86_64 前提で検証しているため
- AMI は **Ubuntu Server 24.04 LTS(Canonical 公式、素の AMI)**。GPU がないので Deep Learning AMI は不要で、Docker は手順書 [deployment-guide.md](deployment-guide.md) §0.1 で導入します

## 3. ストレージ(EBS)

| ノード | 推奨 | サイジングの考え方 |
|---|---|---|
| Node A | **gp3 200GB〜** | モデル本体(HF 形式)+ HF キャッシュで実質モデルサイズの 2〜3 倍。40GB 級 VRAM を使うモデルなら 200GB が安全圏 |
| Node B | **gp3 100GB〜**(案3 は 200GB〜) | TEI のモデルキャッシュ(数 GB)+ ベクトル/全文インデックス + 投入文書。案3 は OpenSearch のインデックスが支配的で、コーパス増に応じて拡張 |

gp3 は既定(3,000 IOPS)で十分です。OpenSearch のインデクシングが遅い場合のみ IOPS/スループットの引き上げを検討します。

## 4. ネットワーク / セキュリティグループ

- 両ノードは**同一 VPC・同一 AZ**に配置する(ノード間はプライベート IP で通信。AZ を跨ぐとレイテンシと転送費用が発生)
- 手順書の ufw の役割は **セキュリティグループ(SG)** で代替する:

| ルール | 送信元 | 宛先 | ポート |
|---|---|---|---|
| vLLM API | Node B の SG | Node A | 8080/tcp |
| WebUI(案1/案2/案3) | 利用者ネットワーク(社内 CIDR 等) | Node B | 8000 / 3000 / 443 |
| SSH 管理 | 管理端末の CIDR(または SSM Session Manager を使い閉じる) | 両ノード | 22/tcp |

- vLLM の `--api-key` は SG があっても設定する(多層防御。[deploy/node-a/.env.example](../deploy/node-a/.env.example) の `VLLM_API_KEY`)
- Node B の docker-compose がデバッグ用に開けるポート(6333/8081/8082/9200 等)は `127.0.0.1` バインド済みのため、SG 側の許可は不要

## 5. 料金目安(月額)

東京リージョン(ap-northeast-1)・Linux・**オンデマンド**単価(2026-07 時点、AWS Price List 由来)による試算。**1USD = 160JPY 換算**、常時稼働は 730h/月、日中帯のみ稼働は 160h/月 で計算。

| Instance Type | 想定用途 | 単価(USD/h) | 常時稼働 730h(円/月) | 日中帯のみ 160h(円/月) |
|---|---|---:|---:|---:|
| **g6e.xlarge** | Node A(最小) | 2.699 | 約 315,200 | 約 69,100 |
| **g6e.2xlarge** | Node A(推奨) | 3.252 | 約 379,800 | 約 83,200 |
| t3.large | Node B 案1(最小) | 0.1088 | 約 12,700 | 約 2,800 |
| m7i.xlarge | Node B 案1 推奨 / 案2 最小 | 0.2604 | 約 30,400 | 約 6,700 |
| m7i.2xlarge | Node B 案2(推奨) | 0.5208 | 約 60,800 | 約 13,300 |
| r7i.xlarge | Node B 案3(最小) | 0.3192 | 約 37,300 | 約 8,200 |
| r7i.2xlarge | Node B 案3(推奨) | 0.6384 | 約 74,600 | 約 16,300 |

**構成例(Node A + Node B の合算)**

| 構成 | 常時稼働(円/月) | 日中帯のみ(円/月) |
|---|---:|---:|
| 検証最小(g6e.xlarge + t3.large) | 約 327,900 | 約 71,900 |
| 案2 常用(g6e.2xlarge + m7i.2xlarge) | 約 440,600 | 約 96,500 |
| 案3 常用(g6e.2xlarge + r7i.2xlarge) | 約 454,400 | 約 99,500 |

**留意点**

- コストの支配項は **Node A(GPU)で、全体の 8〜9 割**を占める。日中帯のみの停止運用(EC2 は停止中 EBS 課金のみ)にするだけで GPU 費用は約 1/4.6 になるため、検証フェーズは**夜間・休日停止の運用を強く推奨**(cron / EventBridge スケジューラ等で自動化)
- 上記は EC2 インスタンス費のみ。**EBS(gp3: 約 0.096 USD/GB・月 ≒ 200GB で約 3,100 円/月)とデータ転送費は別途**
- 常時稼働が確定したら、1 年リザーブドインスタンス / Savings Plans で GPU は 3〜4 割安くなる(例: g6e.xlarge の 1 年 RI は約 1.70 USD/h)
- 単価・為替は変動するため、稟議・予算化の際は [AWS 料金計算ツール](https://calculator.aws/) で最新値を再計算すること

## 6. 参考情報

- [Amazon EC2 G6e インスタンス](https://aws.amazon.com/ec2/instance-types/g6e/)(L40S 48GB/GPU、最大 8 GPU)
- [EC2 高速コンピューティングインスタンス仕様](https://docs.aws.amazon.com/ec2/latest/instancetypes/ac.html)
- [Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 24.04)](https://docs.aws.amazon.com/dlami/latest/devguide/aws-deep-learning-base-gpu-ami-ubuntu-24-04.html)(ドライバ / CUDA / Docker / NVIDIA Container Toolkit 同梱、G6e 対応)
