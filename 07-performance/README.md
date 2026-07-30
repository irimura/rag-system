# 性能測定

Locust から nginx 経由で Open WebUI へストリーミング負荷を与え、TTFT、TPOT(ITL)、Output token throughput、Request throughput の 4 指標を測定します。

> コマンド中の `${...}` は環境に合わせて置換してください。

## ディレクトリ構成

| パス | 内容 |
|---|---|
| [setup.md](setup.md) | perf-001 のセットアップ手順 |
| [procedure.md](procedure.md) | 4 指標による性能試験の準備、実行、判定、記録、クリーンアップ手順 |
| [locustfile.py](locustfile.py) | Open WebUI 用 Locust シナリオ |

## 全体フロー

```mermaid
flowchart LR
    PERF["perf-001<br/>Locust"] -->|"HTTPS :443<br/>POST /api/chat/completions"| NGINX["Node B<br/>nginx"]
    NGINX --> OWUI["Open WebUI"]
    OWUI --> RAG["RAG API<br/>※案2・案3"]
    OWUI -->|"案1b"| A["Node A<br/>vLLM :8080"]
    RAG -->|"案2・案3"| A
```

## 手順

1. [perf-001 をセットアップする](setup.md)。
2. [性能試験を実行し、結果を記録して会話履歴をクリーンアップする](procedure.md)。
