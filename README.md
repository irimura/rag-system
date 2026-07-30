# vLLM + LangChain RAG システム

vLLM の OpenAI 互換 API と LangChain を中心に、日本語 RAG を設計・構築・評価するためのリポジトリです。GPU 推論専用の Node A(GPTQ 4bit) / Node A-2(GPTQ 8bit) / Node A-3(16bit 非量子化)と、アプリ・データ用の Node B を分離します。Ubuntu 24.04、Ampere 世代以降・各モデルに必要な VRAM 40GB または 80GB 以上・CUDA 12.8 対応の GPU、無償利用可能かつソース公開されたソフトウェアを前提とします。

| 工程 | 内容 | ディレクトリ |
|---|---|---|
| 設計 | 全体構成・実装案・認証・ノード仕様 | [01-design/](01-design/README.md) |
| 構築 | AWS・GPU 3 ノードの構築 | [02-provisioning/](02-provisioning/README.md) |
| デプロイ | Node B と RAG アプリの配置 | [03-deployment/](03-deployment/README.md) |
| コーパス取り込み | 公開データの取得・前処理・投入 | [04-corpus/](04-corpus/README.md) |
| 精度評価 | Retrieval・回答品質・認可の評価 | [05-evaluation/](05-evaluation/README.md) |
| チューニング | RAG 構成要素の調整 | [06-tuning/](06-tuning/README.md) |
| 性能測定 | 応答時間の測定(Locust) | [07-performance/](07-performance/README.md) |

実装4案(案1、案1b、案2、案3)の比較サマリは [設計資料 §3](01-design/README.md#3-実装案の比較) を参照してください。
