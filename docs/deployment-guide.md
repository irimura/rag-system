# Node B 構築手順書(案1〜案3)

[deploy/](../deploy/) 配下の Dockerfile / docker-compose.yml / パラメータファイルを使って、アプリ+データノード(Node B)を構築する手順です。

| 案 | 構築ファイル | 公開ポート | 主なパラメータファイル |
|---|---|---|---|
| 案1 | [deploy/plan1/](../deploy/plan1/) | 8000(Chainlit) | `.env` |
| 案2 | [deploy/plan2/](../deploy/plan2/) | 3000(Open WebUI) | `.env` |
| 案3 | [deploy/plan3/](../deploy/plan3/) | 80/443(Nginx) | `.env`、`nginx/conf.d/rag.conf`、`opensearch/index-mapping.json` |

> デバッグ用ポート(Qdrant 6333、TEI 8081/8082、rag-api 8000、OpenSearch 9200)は `127.0.0.1` バインドで外部非公開。Node A(vLLM)には一切手を入れません。

> 以降のコマンド例中の `${node_a}` `${node_b}` `${node_b_ip}` `${node_b_hostname}` `${vllm_api_key}` `${repo_url}` `${n}`(構築する案番号 1/2/3)は、実行前に環境に応じた値に置き換えてください。

## 0. 前提条件

- Node B: Ubuntu Server 22.04 / 24.04(RAM 目安 — 案1: 8GB〜 / 案2: 16GB〜 / 案3: 32GB〜)
- Node A で vLLM が **OpenAI 互換エンドポイントとしてサービス化済み**で、Node B から HTTP 到達できること(未了の場合は先に [node-a-vllm.md](node-a-vllm.md) を実施)
- インターネット接続(イメージ・モデルの初回ダウンロードに必要)

### 0.1 Docker のインストール(Node B)

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-v2
sudo usermod -aG docker $USER   # 再ログインで反映
docker version && docker compose version
```

### 0.2 Node A への疎通確認

```bash
curl http://${node_a}:8080/v1/models -H "Authorization: Bearer ${vllm_api_key}"
# vLLM のモデル一覧(JSON)が返れば OK。返らない場合は Node A 側の
# サービス化(node-a-vllm.md)と FW(8080/tcp が Node B から許可)を確認する
```

### 0.3 リポジトリの配置と共通設定

```bash
git clone ${repo_url} && cd rag-system/deploy/plan${n}
cp -v .env.example .env
vim .env    # 最低限 VLLM_BASE_URL / VLLM_MODEL を実環境に合わせる
            # 案2/3 は WEBUI_SECRET_KEY(案3 は POSTGRES_PASSWORD も)を必ず変更:
            #   openssl rand -hex 32
```

取り込みたい文書(PDF / Markdown / テキスト)を `documents/` に配置します。

---

## 1. 案1 の構築(Chainlit 単一コンテナ)

```bash
cd deploy/plan1

# 1) ビルド(CPU 版 PyTorch + sentence-transformers を含むため数分かかる)
docker compose build

# 2) 取り込み(初回は embedding モデルのダウンロードが走る)
docker compose --profile ingest run --rm ingest

# 3) 起動
docker compose up -d

# 4) 確認
docker compose logs -f chainlit-app     # "Your app is available" が出るまで待つ
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000   # -> 200
```

ブラウザで `http://${node_b}:8000` を開き、投入した文書について質問して回答と「参考資料」表示を確認します。

- 文書を追加・更新したら手順 2) を再実行(インデックスは Docker volume `chroma-data` に永続化)
- 初回質問は rerank モデルのロードで数十秒かかることがある(2 回目以降は高速)

## 2. 案2 の構築(Open WebUI + Qdrant + TEI)

```bash
cd deploy/plan2

# 1) ビルドと起動(TEI は初回起動時にモデルを自動ダウンロード)
docker compose up -d --build

# 2) 各サービスの起動確認
curl http://localhost:8081/health        # tei-embed  -> 200(モデル DL 完了まで数分待つ)
curl http://localhost:8082/health        # tei-rerank -> 200
curl http://localhost:6333/readyz        # qdrant     -> 200
curl http://localhost:8000/health        # rag-api    -> {"status":"ok"}

# 3) 取り込み
docker compose --profile ingest run --rm ingest

# 4) RAG API の動作確認(Open WebUI を通さず直接)
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"knowledge-rag","messages":[{"role":"user","content":"(文書に関する質問)"}]}'
```

**Open WebUI の初期設定**: `http://${node_b}:3000` を開き、最初に作成したアカウントが管理者になります。`OPENAI_API_BASE_URL` で rag-api を接続済みのため、モデル一覧に `knowledge-rag`(`.env` の `RAG_MODEL_NAME`)が表示されればそれを選んで会話を開始できます。

## 3. 案3 の構築(Nginx + OpenSearch ハイブリッド + PostgreSQL)

```bash
cd deploy/plan3

# 1) OpenSearch のカーネル要件(必須。恒久化は /etc/sysctl.d/ に記載)
sudo sysctl -w vm.max_map_count=262144
echo "vm.max_map_count=262144" | sudo tee /etc/sysctl.d/99-opensearch.conf

# 2) TLS 証明書の配置(検証用は自己署名。本番は社内 CA / Let's Encrypt)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/certs/server.key -out nginx/certs/server.crt \
  -subj "/CN=${node_b_hostname}"

# 3) ビルドと起動(opensearch イメージは kuromoji プラグインを組み込みビルド)
docker compose up -d --build

# 4) 起動確認
curl http://localhost:9200/_cluster/health   # status green/yellow で OK
curl http://localhost:9200/_cat/plugins      # analysis-kuromoji があること
curl http://localhost:8081/health && curl http://localhost:8082/health
curl http://localhost:8000/health

# 5) 取り込み(インデックス作成 + BM25/ベクトル同時登録)
docker compose --profile ingest run --rm ingest

# 6) ハイブリッド検索の確認(BM25 側)
curl -s "http://localhost:9200/knowledge/_search" -H "Content-Type: application/json" \
  -d '{"query":{"match":{"text":"(文書中のキーワード)"}},"size":3}'
```

ブラウザで `https://${node_b}/` を開き(自己署名の場合は警告を承認)、管理者アカウントを作成して `knowledge-rag` モデルで会話します。会話履歴・ユーザー情報は PostgreSQL に保存されます。

- `.env` の `OS_HEAP` は Node B の RAM に合わせる(RAM の 25〜50%、32GB 以下)
- OpenSearch はセキュリティプラグイン無効(`DISABLE_SECURITY_PLUGIN=true`)の内部ネットワーク限定構成。9200 を外部公開する場合は必ず有効化し認証を設定する

## 4. 運用

| 作業 | コマンド |
|---|---|
| 文書の追加・再取り込み | `documents/` を更新 → `docker compose --profile ingest run --rm ingest`(全再構築は `FORCE_RECREATE=1` を前置) |
| ログ確認 | `docker compose logs -f <service>` |
| 停止 / 再開 | `docker compose down` / `docker compose up -d`(volume は保持される) |
| アプリ更新 | ソース修正 → `docker compose up -d --build` |
| バックアップ | volume を停止中にアーカイブ: `docker run --rm -v plan2_qdrant-data:/from -v $(pwd):/to alpine tar czf /to/qdrant-backup.tgz -C /from .`(対象: 案1 `chroma-data` / 案2 `qdrant-data`, `open-webui-data` / 案3 `opensearch-data`, `pg-data`, `open-webui-data`) |

## 5. トラブルシューティング

| 症状 | 原因と対処 |
|---|---|
| rag-api が 503「コレクション/インデックスがありません」 | ingest 未実行。§1〜3 の取り込み手順を実行する |
| TEI が起動直後に応答しない | 初回のモデルダウンロード中。`docker compose logs tei-embed` で進捗確認(volume `hf-cache` にキャッシュされ 2 回目以降は速い) |
| OpenSearch が起動ループ | `vm.max_map_count` 未設定(§3-1)、またはヒープ過大。`docker compose logs opensearch` を確認 |
| 回答が「資料からは回答できません」ばかり | ①ingest 済みか ②`RERANK_THRESHOLD` が高すぎないか(0 にして切り分け)③質問が文書内容と合っているか、を順に確認 |
| vLLM への接続エラー | `.env` の `VLLM_BASE_URL` と §0-2 の疎通を確認(コンテナ内からは `localhost` は使えない — Node A の実ホスト名/IP を指定する) |
| Embedding モデルを変えたら検索が壊れた | ベクトル空間の互換性はない。`FORCE_RECREATE=1` で全再取り込み(案3 は `.env` の `EMBED_DIM` も合わせる) |
| e5 系モデルで精度が悪い | 案1 は `common.py` が prefix を自動付与。案2/3 の TEI 構成で e5 系を使う場合は query:/passage: の付与処理を追加する必要がある(既定の bge-m3 は不要) |

## 6. 動作確認チェックリスト(受け入れ)

1. WebUI にアクセスでき、モデル(`knowledge-rag` / 案1 は Chainlit 画面)が使える
2. 投入した文書の内容を質問すると、本文に基づいた回答 + 参考資料(ファイル名)が返る
3. 文書に存在しない事柄を質問すると「資料からは回答できません」と返る(捏造しない)
4. `docker compose restart` 後もインデックスと(案2/3)会話履歴が保持されている
5. 以降の精度評価は [evaluation-spec.md](evaluation-spec.md) の手順で実施する
