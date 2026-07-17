# vLLM + LangChain RAG システム

vLLM の OpenAI 互換 API と LangChain を中心に、日本語 RAG を設計・構築・評価するためのリポジトリです。GPU 推論専用の Node A とアプリ・データ用の Node B を分離し、Ubuntu 24.04、Ampere 世代以降・VRAM 40GB 以上・CUDA 12.8 対応の GPU、無償利用可能かつソース公開されたソフトウェアを前提とします。

| 工程 | ディレクトリ |
|---|---|
| 設計 | [01-design/](01-design/README.md) |
| 構築 | [02-provisioning/](02-provisioning/aws-provisioning.md) |
| デプロイ | [03-deployment/](03-deployment/deployment-guide.md) |
| コーパス取り込み | [04-corpus/](04-corpus/README.md) |
| 精度評価 | [05-evaluation/](05-evaluation/README.md) |
| チューニング | [06-tuning/](06-tuning/rag-components.md) |

実装4案(案1、案1b、案2、案3)の比較サマリは [設計資料 §3](01-design/README.md#3-実装案の比較) を参照してください。