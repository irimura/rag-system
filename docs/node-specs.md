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

### 1.1 選定基準

GPU インスタンスの選定は、次の順で絞り込みます。

1. **GPU の VRAM が決定打**(vCPU/RAM は二の次)。要件の VRAM 40GB 以上を**単一 GPU** で満たせるファミリーを選ぶ。複数 GPU の合算でも `--tensor-parallel-size` で動くが、通信オーバーヘッドと運用の複雑さが増すため、載るなら 1 枚に載せるのが基本
2. **ホスト RAM はモデルサイズ以上**を確保する(モデルロード時に読み込むため。VRAM 40GB を使い切るモデルならホスト RAM 64GB が安全)
3. vCPU はトークナイズ・前処理程度なので 4〜8 で足りる
4. 推論はネットワーク負荷が小さいので帯域は既定で十分

### 1.2 候補の比較(2026-07 時点)

| Instance Type | GPU | VRAM | vCPU / RAM | 判定 |
|---|---|---|---|---|
| **g6e.xlarge** | L40S ×1 | **48GB** | 4 / 32GB | ○ 最小構成(コスト優先) |
| **g6e.2xlarge** | L40S ×1 | **48GB** | 8 / 64GB | **◎ 推奨**(ホスト RAM に余裕) |
| g6.xlarge / g5.xlarge | L4 / A10G ×1 | 24GB | - | × VRAM 不足(40GB 未満) |
| g6e.12xlarge | L40S ×4 | 192GB | 48 / 384GB | △ 70B 級 bf16 等、1 枚に載らない場合のみ(`--tensor-parallel-size 4`) |
| p4d / p5 系 | A100 / H100 ×8 | 320GB〜 | - | × 本用途にはオーバースペック(8 GPU 固定で高額) |

- **g6e ファミリー(NVIDIA L40S 48GB/GPU)が「単一 GPU で 40GB+」を満たす最も経済的な選択肢**です。同じ 1 GPU なら xlarge / 2xlarge / 4xlarge の VRAM は同じ 48GB で、差は vCPU / ホスト RAM のみ
- g6e.xlarge(ホスト RAM 32GB)は、VRAM 40GB を使い切るサイズのモデルをロードする際にホスト RAM が窮屈になり得るため、**g6e.2xlarge を推奨**とします。まず xlarge で始めて、ロード時のメモリ不足やスワップが出たら 2xlarge に上げる進め方でも問題ありません
- 料金は変動するため、確定時に [EC2 オンデマンド料金表](https://aws.amazon.com/ec2/pricing/on-demand/) で対象リージョンの単価を確認してください。検証フェーズは停止(EBS のみ課金)をこまめに行うとコストを抑えられます

### 1.3 AMI

**Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 24.04)** — ご想定の名称で正しく、G6e をサポート対象に含みます。NVIDIA ドライバ・CUDA・**Docker・NVIDIA Container Toolkit が導入済み**のため、[node-a-vllm.md](node-a-vllm.md) §1.1(Toolkit 導入)は**スキップ**できます。

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
| 案1 | t3.large(2vCPU/8GB) | m7i.xlarge(4vCPU/16GB) | embedding/rerank がプロセス内 CPU 実行のため vCPU 多めが快適 |
| 案2 | m7i.xlarge(4vCPU/16GB) | m7i.2xlarge(8vCPU/32GB) | TEI ×2 + Qdrant + WebUI |
| 案3 | r7i.xlarge(4vCPU/32GB) | **r7i.2xlarge(8vCPU/64GB)** | OpenSearch の JVM ヒープ(`OS_HEAP`)+ヒープ外メモリでメモリ優先型(r 系)が適する |

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

- vLLM の `--api-key` は SG があっても設定する(多層防御。[node-a-vllm.md](node-a-vllm.md) §5)
- Node B の docker-compose がデバッグ用に開けるポート(6333/8081/8082/9200 等)は `127.0.0.1` バインド済みのため、SG 側の許可は不要

## 5. 参考情報

- [Amazon EC2 G6e インスタンス](https://aws.amazon.com/ec2/instance-types/g6e/)(L40S 48GB/GPU、最大 8 GPU)
- [EC2 高速コンピューティングインスタンス仕様](https://docs.aws.amazon.com/ec2/latest/instancetypes/ac.html)
- [Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 24.04)](https://docs.aws.amazon.com/dlami/latest/devguide/aws-deep-learning-base-gpu-ami-ubuntu-24-04.html)(ドライバ / CUDA / Docker / NVIDIA Container Toolkit 同梱、G6e 対応)
