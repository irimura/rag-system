# ノードスペック選定(AWS EC2)

本設計は特定クラウドのマネージドサービスを使わない構成のため、EC2 は「素の Ubuntu VM」として利用します(オンプレミスに置き換える場合も本書の CPU/RAM/GPU 要件がそのまま基準になります)。

> **ノード名の対応に注意**: 本リポジトリでは一貫して **Node A / Node A-2 / Node A-3 = GPU ノード(vLLM、NVIDIA Container Toolkit 必要)/ Node B = アプリ+データノード(GPU 不要)** と定義しています。GPU 要件・GPU AMI が付くのは **Node A 系 3 ノード**です。

## サマリ

| ノード | 役割 | Instance Type(推奨) | AMI |
|---|---|---|---|
| **Node A** | vLLM / GPTQ 4bit・最大 32k(推論専用) | **g6e.2xlarge**(最小: g6e.xlarge) | Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 24.04) |
| **Node A-2** | vLLM / GPTQ 8bit・最大 16k(推論専用) | **g6e.2xlarge**(最小: g6e.xlarge) | 同上 |
| **Node A-3** | vLLM / 16bit 非量子化・最大 32k(推論専用) | **p5.4xlarge**(単一 H100 80GB。代替案は §1.3) | 同上 |
| **Node B** | WebUI / RAG API / ベクトル DB / TEI | 案毎に下表(例: 案2 は m7i.xlarge〜) | Ubuntu Server 24.04 LTS(Canonical 公式) |
| **性能測定ノード** | Locust による負荷生成 | **t3.medium** | Ubuntu Server 24.04 LTS(Canonical 公式) |

---

## 1. Node A 系(GPU ノード)の選定

### 1.1 要求スペック(確定要件)

利用する vLLM と LLM の要件として以下が確定しています。「量子化」は Qdrant のベクトル量子化ではなく、LLM の**重み量子化(GPTQ)**を指します。

| ノード | GPU 世代 | VRAM | 最大シーケンス長 | LLM の重み形式 | vLLM 起動パラメータ |
|---|---|---:|---:|---|---|
| **Node A(既存)** | Ampere 世代以降 | **40GB 以上** | **32k** | **GPTQ 4bit** | `--max-model-len 32768 --gpu-memory-utilization 0.90` |
| **Node A-2(新規)** | Ampere 世代以降 | **40GB 以上** | **16k** | **GPTQ 8bit** | `--max-model-len 16384 --gpu-memory-utilization 0.90` |
| **Node A-3(新規)** | Ampere 世代以降 | **80GB 以上** | **32k** | **16bit(非量子化)** | `--max-model-len 32768 --gpu-memory-utilization 0.90`。2×L40S 案のみ `--tensor-parallel-size 2` |

全ノード共通で CUDA **12.8 対応**(NVIDIA Driver は 570 系以降)、**NVIDIA Driver**、**NVIDIA Container Toolkit**が必要です。

- ソフトウェア要件は後述の Deep Learning Base OSS Nvidia Driver GPU AMI で充足できる(§1.4)。導入済みドライバが CUDA 12.8 に対応しているかは、AMI のリリースノートと起動後の `nvidia-smi`(右上の CUDA Version 表示が 12.8 以上)で確認する
- venv + systemd 方式([02-provisioning/node-a/vllm.service](../02-provisioning/node-a/vllm.service))を採る場合、NVIDIA Container Toolkit は不要(Driver のみ必須)

### 1.2 選定基準

GPU インスタンスの選定は、次の順で絞り込みます。

1. **GPU 世代と VRAM が決定打**(vCPU/RAM は二の次)。必要 VRAM を**単一 GPU**で満たすのが原則。例外として Node A-3 は、単一 80GB GPU の調達性・コストと比較したうえで 2×L40S(合計 96GB、`--tensor-parallel-size 2`)を許容する
2. **ホスト RAM はモデルファイルのサイズ以上**を確保する。Node A / A-2 は 64GB を推奨し、16bit モデルを読む Node A-3 はロード時の一時領域も含めて特に余裕を持たせる
3. vCPU はトークナイズ・前処理程度なので 4〜8 で足りる
4. 推論はネットワーク負荷が小さいので帯域は既定で十分

### 1.3 候補の比較(2026-07 時点)

| 対象ノード | Instance Type | GPU(世代) | 搭載 VRAM | vCPU / RAM | 判定・使用方法 |
|---|---|---|---:|---|---|
| A / A-2 | **g6e.xlarge** | L40S ×1(Ada Lovelace) | **48GB** | 4 / 32GB | ○ 最小構成(コスト優先) |
| A / A-2 | **g6e.2xlarge** | L40S ×1(同上) | **48GB** | 8 / 64GB | **◎ 推奨**(ホスト RAM に余裕) |
| A / A-2 | g5.xlarge | A10G ×1(Ampere) | 24GB | - | × VRAM 不足 |
| A / A-2 | g6.xlarge | L4 ×1(Ada Lovelace) | 24GB | - | × VRAM 不足 |
| A-3 | **p5.4xlarge** | H100 ×1(Hopper) | **80GB** | 16 / 256GB | **◎ 単一 GPU 推奨案**。現行原則どおり TP=1 |
| A-3 | p4de.24xlarge | A100 80GB ×8(Ampere) | 640GB | 96 / 1,152GB | × 単一 GPU だけで要件を満たすが、8 GPU 固定の課金で本用途には大幅なオーバースペック |
| A-3 | p5.48xlarge | H100 80GB ×8(Hopper) | 640GB | 192 / 2,048GB | × 単一 GPU だけで要件を満たすが、8 GPU 固定の課金で本用途には大幅なオーバースペック |
| A-3 | **g6e.12xlarge** | L40S ×4(Ada Lovelace) | 192GB | 48 / 384GB | ○ **2 GPU(96GB)のみ使用、TP=2**。残る 2 GPU 分もインスタンス料金に含まれる |

- **g6e ファミリー(NVIDIA L40S 48GB/GPU、Ada Lovelace 世代)が「Ampere 以降 + 単一 GPU で 40GB+」を満たす最も経済的な選択肢**です。L40S は CUDA 12.8 対応です。同じ 1 GPU なら xlarge / 2xlarge / 4xlarge の VRAM は同じ 48GB で、差は vCPU / ホスト RAM のみ
- g6e.xlarge(ホスト RAM 32GB)は、VRAM 40GB を使い切るサイズのモデルをロードする際にホスト RAM が窮屈になり得るため、**g6e.2xlarge を推奨**とします。まず xlarge で始めて、ロード時のメモリ不足やスワップが出たら 2xlarge に上げる進め方でも問題ありません
- Node A-3 は **p5.4xlarge の単一 H100 80GB**が GPU 数と料金の対応が最も素直です。p4de.24xlarge / p5.48xlarge は 8 GPU 全体への課金となります。g6e.12xlarge は 4×L40S 搭載ですが本要件では 2 GPU だけを TP=2 で使うため、GPU 間通信のオーバーヘッドに加え、未使用 2 GPU 分のコストも負担します
- p5.4xlarge は比較的新しいサイズのため、**東京リージョンでの提供有無と単価を確定時に EC2 料金表で必ず確認**します
- 月額の試算は §6 を参照。料金は変動するため、確定時に [EC2 オンデマンド料金表](https://aws.amazon.com/ec2/pricing/on-demand/) で対象リージョンの単価を確認してください。検証フェーズは停止(EBS のみ課金)をこまめに行うとコストを抑えられます

### 1.4 AMI

**Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 24.04)** — G6e をサポート対象に含みます。§1.1 の必須ソフトウェア(NVIDIA Driver・**Docker・NVIDIA Container Toolkit**)が導入済みのため、Toolkit の個別導入は不要で、[02-provisioning/node-a/](../02-provisioning/node-a/) の `docker compose up -d` から直接始められます。最新版 AMI のドライバが CUDA 12.8 に対応していることをリリースノートで確認して選択してください。

- 「Base」が付かない DLAMI(PyTorch 入り等)はフレームワーク同梱で大きいだけなので不要。vLLM はコンテナ(または venv)で導入するため Base で十分
- カーネルの自動更新はドライバ互換性を壊すことがあるため、AMI のガイダンスに従いセキュリティパッチ以外のカーネル更新は避ける

## 2. Node B(アプリ+データノード)の選定

### 2.1 選定基準

1. **RAM が決定打**(採用する案の常駐サービス数で決まる): 案1/案1b 8GB〜 / 案2 16GB〜 / 案3 32GB〜
2. **vCPU は TEI(embedding/rerank の CPU 推論)が主な消費者**。対話のレイテンシと取り込みバッチの速度に効くため 4 vCPU 以上を推奨
3. GPU は不要(GPU AMI も不要)。取り込みが遅い場合の GPU 追加は後から検討([plan2 参照](plan2-standard.md))
4. バーストが許容できる検証用途なら t3/t4g 系、常用なら非バーストの m/r 系

### 2.2 案毎の推奨

| 案 | 最小(検証) | 推奨(常用) | 備考 |
|---|---|---|---|
| 案1/案1b | t3.large(2vCPU/8GB) | m7i.xlarge(4vCPU/16GB) | embedding/rerank が Node B の CPU で動くため vCPU 多めが快適 |
| 案2 | m7i.xlarge(4vCPU/16GB) | m7i.2xlarge(8vCPU/32GB) | TEI ×2 + Qdrant + WebUI |
| 案3 | r7i.xlarge(4vCPU/32GB) | **r7i.2xlarge(8vCPU/64GB)** | OpenSearch の JVM ヒープ(`OS_HEAP`)+ヒープ外メモリでメモリ優先型(r 系)が適する |

案1b・案2への NGINX 追加のオーバーヘッドは軽微(常駐数十 MB)のため、推奨 Instance Type は据え置きとします。

- m7i/r7i(Intel)は例示です。同世代の AMD(m7a/r7a)は同スペックでやや安価なので、リージョンの提供状況と単価で選んで構いません
- **ARM(Graviton, m7g/r7g)は避けてください**。本構成のコンテナイメージ(TEI CPU 版等)は x86_64 前提で検証しているため
- AMI は **Ubuntu Server 24.04 LTS(Canonical 公式、素の AMI)**。GPU がないので Deep Learning AMI は不要で、Docker は手順書 [デプロイ手順書](../03-deployment/README.md) §0.1 で導入します

## 3. 性能測定ノード(perf-001)の選定

Locust の負荷生成専用ノードには **t3.medium(2vCPU/4GB)** を採用します。負荷生成側は HTTP リクエストの送信と統計集計が中心で、Node A / Node B のようなモデル推論・検索インデックス保持を行わないため、CPU・メモリ要件は小さい構成です。ルート EBS は Ubuntu、Python 仮想環境、Locust、測定結果を収容する **gp3 30GB** とします。

高い同時実行数で perf-001 自身の CPU 使用率が飽和し、RPS が対象システムではなく負荷生成側に制限される場合は、Locust の worker 分散またはインスタンスタイプの拡張を検討します。

## 4. ストレージ(EBS)

| ノード | 推奨 | サイジングの考え方 |
|---|---|---|
| Node A | **gp3 200GB〜** | GPTQ 4bit モデル本体 + HF キャッシュ。実ファイルサイズの 2〜3 倍を確保 |
| Node A-2 | **gp3 200GB〜** | GPTQ 8bit モデル本体 + HF キャッシュ。実ファイルサイズの 2〜3 倍を確保し、不足時は拡張 |
| Node A-3 | **gp3 300GB〜** | 16bit モデルは GPTQ 版より大きい。モデル取得後の実ファイルサイズを確認し、その 2〜3 倍へ再計算(大規模モデルは 300GB を超えて拡張) |
| Node B | **gp3 100GB〜**(案3 は 200GB〜) | TEI のモデルキャッシュ(数 GB)+ ベクトル/全文インデックス + 投入文書。案3 は OpenSearch のインデックスが支配的で、コーパス増に応じて拡張 |
| 性能測定ノード | **gp3 30GB** | Ubuntu、Python 仮想環境、Locust、CSV 測定結果を収容 |

gp3 は既定(3,000 IOPS)で十分です。OpenSearch のインデクシングが遅い場合のみ IOPS/スループットの引き上げを検討します。

## 5. ネットワーク / セキュリティグループ

- Node A / A-2 / A-3、Node B、性能測定ノードは**同一 VPC・同一 AZ**に配置する(ノード間はプライベート IP で通信。AZ を跨ぐとレイテンシと転送費用が発生)
- 手順書の ufw の役割は **セキュリティグループ(SG)** で代替する
- 全ノード役割には同じ SG を付与し、**同一 SG 内の通信を相互許可する自己参照ルール**を設定する。これにより Node B から全 GPU ノードの 8080/tcp、perf-001 から Node B の 443/tcp へ到達できる

| ルール | 送信元 | 宛先 | ポート |
|---|---|---|---|
| vLLM API | 同一 SG(Node B 等) | Node A / A-2 / A-3 | 8080/tcp |
| WebUI(案1/案1b/案2/案3) | 利用者ネットワーク(社内 CIDR 等) | Node B | 8000(案1) / 80・443(案1b/案2/案3) |
| SSH 管理 | 管理端末の CIDR(または SSM Session Manager を使い閉じる) | 両ノード | 22/tcp |

- vLLM の `--api-key` は全 GPU ノードで必須とする(単一 SG の自己参照ルールに対する多層防御)。各ノードの `.env.example` の `VLLM_API_KEY` を必ず変更する
- Node B の docker-compose がデバッグ用に開けるポート(6333/8081/8082/9200 等)は `127.0.0.1` バインド済みのため、SG 側の許可は不要

## 6. 料金目安(月額)

東京リージョン(ap-northeast-1)・Linux・**オンデマンド**単価(2026-07 時点、AWS Price List 由来)による試算。**1USD = 160JPY 換算**、常時稼働は 730h/月、日中帯のみ稼働は 160h/月 で計算。

| Instance Type | 想定用途 | 単価(USD/h) | 常時稼働 730h(円/月) | 日中帯のみ 160h(円/月) |
|---|---|---:|---:|---:|
| **g6e.xlarge** | Node A(最小) | 2.699 | 約 315,200 | 約 69,100 |
| **g6e.2xlarge** | Node A(推奨) | 3.252 | 約 379,800 | 約 83,300 |
| **p5.4xlarge** | Node A-3(単一 GPU 推奨) | 8.600 | 約 1,004,500 | 約 220,200 |
| g6e.12xlarge | Node A-3(TP=2、4 GPU 分課金) | 15.217 | 約 1,777,300 | 約 389,600 |
| p4de.24xlarge | Node A-3(8 GPU 固定、比較用) | 37.6223 | 約 4,394,300 | 約 963,100 |
| p5.48xlarge | Node A-3(8 GPU 固定、比較用) | 68.800 | 約 8,035,800 | 約 1,761,300 |
| t3.medium | 性能測定ノード | 0.0544 | 約 6,400 | 約 1,400 |
| t3.large | Node B 案1/案1b(最小) | 0.1088 | 約 12,700 | 約 2,800 |
| m7i.xlarge | Node B 案1/案1b 推奨 / 案2 最小 | 0.2604 | 約 30,400 | 約 6,700 |
| m7i.2xlarge | Node B 案2(推奨) | 0.5208 | 約 60,800 | 約 13,300 |
| r7i.xlarge | Node B 案3(最小) | 0.3192 | 約 37,300 | 約 8,200 |
| r7i.2xlarge | Node B 案3(推奨) | 0.6384 | 約 74,600 | 約 16,300 |

**構成例(GPU 3 ノード + Node B の合算)**

| 構成 | 常時稼働(円/月) | 日中帯のみ(円/月) |
|---|---:|---:|
| 検証最小(A/A-2=g6e.xlarge、A-3=p5.4xlarge、B=t3.large) | 約 1,647,600 | 約 361,200 |
| 案2 常用(A/A-2=g6e.2xlarge、A-3=p5.4xlarge、B=m7i.2xlarge) | 約 1,825,000 | 約 400,100 |
| 案3常用・A-3をTP=2(A/A-2=g6e.2xlarge、A-3=g6e.12xlarge、B=r7i.2xlarge) | 約 2,611,500 | 約 572,500 |

**非インスタンス系サービスの月額(EC2 インスタンス費以外)**

| サービス | 課金モデル | 月額目安(1USD=160JPY・東京) |
|---|---|---|
| VPC / サブネット / ルートテーブル / IGW / Security Group | 無料 | 0 円 |
| EC2 Instance Connect Endpoint(EICE) | エンドポイントは無料(データ転送のみ) | ほぼ 0 円 |
| **EBS gp3** | 確保 GB × 月(**インスタンス停止中も課金**) | 約 15.4 円/GB・月 → 100GB 約 1,540 円 / 200GB 約 3,100 円 |
| EBS スナップショット(AMI 用・任意) | 使用 GB × 月(増分) | 約 8 円/GB・月(1 世代 約 30GB なら 約 240 円) |
| NAT Gateway(一時) | 稼働時間 + 処理データ量 | 約 10 円/h + 約 10 円/GB(定常運用では削除) |
| Elastic IP(NAT 用・一時) | 割当中のみ | 約 0.8 円/h(NAT 稼働中のみ) |

- **EBS が唯一の常時課金項目**(インスタンスを停止しても消えない)。GPU 3 ノードの最小推奨容量は 200GB + 200GB + 300GB。Node B を含む合算は案1/案1b/案2で 800GB ≒ **約 12,300 円/月**、案3で 900GB ≒ **約 13,800 円/月**。
- **NAT Gateway + EIP は一時利用**。例: セットアップ 1 回(約 10h 稼働・モデル/イメージ 100GB ダウンロード)≒ **約 1,100 円/回**。使い終えたら削除して停止する([aws-provisioning.md](../02-provisioning/aws-provisioning.md) §2.2)。
- VPC・IGW・EICE 等は無料。データ転送(外向き egress)は別途だが、定常運用は閉域(IGW/NAT なし)のため EC2 起点の egress はほぼ発生しない。

**留意点**

- コストの支配項は **Node A / A-2 / A-3 の GPU 3 ノード**です。案2常用例では GPU 費用が常時約 176.4 万円/月から日中帯約 38.7 万円/月へ約 137.7 万円下がります。730h と 160h の比率どおり約 78%削減できるため、全 GPU ノードに毎日 18:00 の自動停止を適用し、夜間・休日は停止します
- 上記の Instance Type 表は EC2 インスタンス費のみ。EBS・NAT・その他サービスは前掲「非インスタンス系サービスの月額」を参照
- 常時稼働が確定したら、1 年リザーブドインスタンス / Savings Plans で GPU は 3〜4 割安くなる(例: g6e.xlarge の 1 年 RI は約 1.70 USD/h)
- 単価・為替は変動するため、稟議・予算化の際は [AWS 料金計算ツール](https://calculator.aws/) で最新値を再計算すること

## 7. 参考情報

- [Amazon EC2 G6e インスタンス](https://aws.amazon.com/ec2/instance-types/g6e/)(L40S 48GB/GPU、最大 8 GPU)
- [EC2 高速コンピューティングインスタンス仕様](https://docs.aws.amazon.com/ec2/la05-evaluation/instancetypes/ac.html)
- [Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 24.04)](https://docs.aws.amazon.com/dlami/la05-evaluation/devguide/aws-deep-learning-base-gpu-ami-ubuntu-24-04.html)(ドライバ / CUDA / Docker / NVIDIA Container Toolkit 同梱、G6e 対応)
- [Amazon VPC 料金](https://aws.amazon.com/vpc/pricing/)(NAT Gateway・パブリック IPv4 の単価)/ [Amazon EBS 料金](https://aws.amazon.com/ebs/pricing/)
