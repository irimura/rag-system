# インフラ・Node A 構築ガイド

AWS 上のインフラと Node A(vLLM 推論専用 GPU ノード)を構築する工程です。
スペック選定の根拠は [設計: node-specs.md](../01-design/node-specs.md) を参照してください。

## 手順の使い分け

- **ゼロから 4 ノード一式を構築する** → [aws-provisioning.md](aws-provisioning.md)
  (VPC・サブネット・SG・NAT Gateway・EICE・EC2 の作成/削除/AMI 化を Bash/CLI で実施)
- **Node A だけを単体で事前構築・動作確認する** → [node-a-pre-install.md](node-a-pre-install.md)
  (既存 VPC 前提。DLAMI 確認 → [node-a/](node-a/) による vLLM サービス化・起動確認まで)

構築完了後、次の工程は [03 デプロイ](../03-deployment/README.md)(Node B)です。