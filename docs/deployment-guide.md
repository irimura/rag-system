# Node B 構築手順書(全案)

[deploy/](../deploy/) 配下の Dockerfile / docker-compose.yml / パラメータファイルを使って、アプリ+データノード(Node B)を構築する手順です。

| 案 | 構築ファイル | 公開ポート | 主なパラメータファイル |
|---|---|---|---|
| 案1 | [deploy/plan1/](../deploy/plan1/) | 8000(Chainlit) | `.env` |
| 案1b | [deploy/plan1b/](../deploy/plan1b/) | 3000(Open WebUI) | `.env` |
| 案2 | [deploy/plan2/](../deploy/plan2/) | 3000(Open WebUI) | `.env` |
| 案3 | [deploy/plan3/](../deploy/plan3/) | 80/443(Nginx) | `.env`、`nginx/conf.d/rag.conf`、`opensearch/index-mapping.json` |

> デバッグ用ポート(Qdrant 6333、TEI 8081/8082、rag-api 8000、OpenSearch 9200)は `127.0.0.1` バインドで外部非公開。Node A(vLLM)には一切手を入れません。

> 検証フェーズのコンテナタグと Python requirements はマイナー系列以上を明示して固定済みです。再検証なしに `latest` / `main` へ戻さないでください。digest 固定を含む最終更新方針は運用設計フェーズで決定します。

> 以降のコマンド例中の `${node_a}` `${node_b}` `${node_b_ip}` `${node_b_hostname}` `${vllm_api_key}` `${repo_url}` `${n}`(構築する案番号 1/2/3)は、実行前に環境に応じた値に置き換えてください。

## 0. 前提条件

- Node B: Ubuntu Server 24.04 LTS(RAM 目安 — 案1/案1b: 8GB〜 / 案2: 16GB〜 / 案3: 32GB〜)。AWS EC2 で構築する場合の Instance Type / AMI 選定は [node-specs.md](node-specs.md) を参照
- Node A で vLLM が **OpenAI 互換エンドポイントとしてサービス化済み**で、Node B から HTTP 到達できること(未了の場合は先に [deploy/node-a/](../deploy/node-a/) の compose または systemd unit で `vllm serve` を起動する。スペック・AMI は [node-specs.md](node-specs.md) §1)
- インターネット接続(イメージ・モデルの初回ダウンロードに必要)

### 0.1 Docker のインストール(Node B)

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-v2
sudo usermod -aG docker ${USER}   # 再ログインで反映
docker version && docker compose version
```

### 0.2 Node A への疎通確認

```bash
curl http://${node_a}:8080/v1/models -H "Authorization: Bearer ${vllm_api_key}"
# vLLM のモデル一覧(JSON)が返れば OK。返らない場合は Node A 側の
# サービス化(deploy/node-a/)と FW(8080/tcp が Node B から許可)を確認する
```

### 0.3 リポジトリの配置と共通設定

```bash
git clone ${repo_url} && cd rag-system/deploy/plan${n}
cp -v .env.example .env
vim .env    # 最低限 VLLM_BASE_URL / VLLM_API_KEY(案1/2/3 は VLLM_MODEL も)を実環境に合わせる
            # 案1b/2/3 は WEBUI_SECRET_KEY を変更。案3は加えて
            # OPENSEARCH_INITIAL_ADMIN_PASSWORD / OS_RAG_PASSWORD /
            # OS_INGEST_PASSWORD / POSTGRES_PASSWORD も別々の値へ変更:
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

- 文書を追加・更新・削除したら `documents/` に全コーパスが揃っていることを確認して手順 2) を再実行する。既存コレクションは削除され、全量再構築される。案1は再取り込み後に `docker compose restart chainlit-app` を実行する
- 初回質問は rerank モデルのロードで数十秒かかることがある(2 回目以降は高速)

## 1b. 案1b の構築(Open WebUI 単体)

```bash
cd deploy/plan1b

# 1) 起動
# 初回は Open WebUI と embedding/rerank モデルをダウンロードする
docker compose up -d

# 2) 確認
docker compose logs -f open-webui
docker compose ps
```

ブラウザで `http://${node_b}:3000` を開き、最初のアカウントを管理者として登録します。管理者設定の OpenAI API 接続で Node A の vLLM モデルが表示され、直接選択できることを確認します。

`Workspace > Knowledge` で文書をアップロードし、チャットでその Knowledge を参照して質問します。回答と出典が表示されれば、内蔵 RAG の取り込み・検索・生成経路を確認できています。

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

案3は OpenSearch Security Plugin を有効にし、コンテナ間も TLS と Basic 認証で接続します。検証フェーズでは固定済み OpenSearch イメージが初回起動時に配置するデモ CA / 証明書を使用します。OpenSearch の起動後に公開 CA 証明書だけをホストへ取り出し、`rag-api` / `security-init` / `ingest` へ読み取り専用でマウントします。`security-init` が初期管理者で `rag_api`(検索専用)と `ingest`(インデックス更新用)を冪等作成し、その完了後に各サービスが起動します。

```bash
cd deploy/plan3

# 1) OpenSearch のカーネル要件(必須。恒久化は /etc/sysctl.d/ に記載)
sudo sysctl -w vm.max_map_count=262144
cat <<'EOF' | sudo tee /etc/sysctl.d/99-opensearch.conf
vm.max_map_count=262144
EOF

# 2) Nginx の TLS 証明書を配置(検証用は自己署名。本番は社内 CA / Let's Encrypt)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/certs/server.key -out nginx/certs/server.crt \
  -subj "/CN=${node_b_hostname}"

# 3) .env の全パスワードを別々の強い値へ変更
# OPENSEARCH_INITIAL_ADMIN_PASSWORD / OS_RAG_PASSWORD / OS_INGEST_PASSWORD /
# WEBUI_SECRET_KEY / POSTGRES_PASSWORD の各値に `openssl rand -hex 32` の結果を設定する
vim .env

# 4) OpenSearch だけを先にビルド・起動し、起動時に配置された公開 CA を取り出す
# root-ca.pem はイメージのビルド時には存在しないため、この順序を変えない
docker compose up -d --build opensearch
docker compose logs -f opensearch             # "started" を確認後 Ctrl-C
mkdir -v -p rag-api/certs
docker compose cp opensearch:/usr/share/opensearch/config/root-ca.pem \
  rag-api/certs/root-ca.pem

# 5) 残りをビルド・起動する
# 先に全イメージをビルドし、手順 4 の OpenSearch コンテナは再作成しない
docker compose build
docker compose up -d
docker compose ps -a security-init
docker compose logs security-init          # 終了コード 0 と設定完了メッセージを確認

# 6) TLS・管理者認証・プラグイン・各サービスの確認
docker compose exec opensearch bash -c \
  'curl --fail --cacert config/root-ca.pem -u "admin:${OPENSEARCH_INITIAL_ADMIN_PASSWORD}" \
  https://node-0.example.com:9200/_cluster/health'
docker compose exec opensearch bash -c \
  'curl --fail --cacert config/root-ca.pem -u "admin:${OPENSEARCH_INITIAL_ADMIN_PASSWORD}" \
  https://node-0.example.com:9200/_cat/plugins'
docker compose exec opensearch bash -c \
  'curl --fail --cacert config/root-ca.pem -u "admin:${OPENSEARCH_INITIAL_ADMIN_PASSWORD}" \
  https://node-0.example.com:9200/_plugins/_security/api/roles/rag_reader'
curl http://localhost:8081/health && curl http://localhost:8082/health
curl http://localhost:8000/health

# 7) 取り込み(ingest 専用ユーザーでインデックス作成 + BM25/ベクトル同時登録)
docker compose --profile ingest run --rm ingest

# 8) rag-api 専用ユーザーで indices.exists が成功し、更新が拒否されることを確認
docker compose exec rag-api python -c \
  'import os; from opensearch_client import build_opensearch_client; print(build_opensearch_client().indices.exists(os.environ["OS_INDEX"]))'
# 次は AuthorizationException(HTTP 403)で失敗すれば正常。文書は作成されない
docker compose exec rag-api python -c \
  'import os; from opensearch_client import build_opensearch_client; build_opensearch_client().index(index=os.environ["OS_INDEX"], body={"n02":"must-be-denied"})'

# 9) rag-api の実検索を確認
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"knowledge-rag","messages":[{"role":"user","content":"(文書に関する質問)"}]}'
```

ブラウザで `https://${node_b}/` を開き(自己署名の場合は警告を承認)、管理者アカウントを作成して `knowledge-rag` モデルで会話します。会話履歴・ユーザー情報は PostgreSQL に保存されます。

- `.env` の `OS_HEAP` は Node B の RAM に合わせる(RAM の 25〜50%、32GB 以下)
- `rag-api` と `ingest` は初期管理者パスワードを受け取らず、別々のサービスユーザーで CA とホスト名を検証する
- `rag-api/certs/root-ca.pem` は生成物であり Git 管理しない。OpenSearch イメージを変更またはコンテナを再作成した場合は、手順 4 で同じコンテナから CA を再取得する
- デモ CA / 証明書と `node-0.example.com` の Docker 内 DNS alias は検証フェーズ専用。本番では組織 CA でノード証明書を発行し、OpenSearch の `opensearch.yml` と `rag-api` の `OS_CA_CERT` を置き換える
- Security Plugin 無効時に作成した既存 volume を引き継ぐ場合は、必要データを退避し、全コーパスから再取り込みできることを確認してから `opensearch-data` を新規作成する。初期管理者パスワードは初回初期化時にのみ反映される

## 4. 運用

| 作業 | コマンド |
|---|---|
| 文書の追加・更新・削除 | 案1/2/3: `documents/` に全コーパスを配置 → `docker compose --profile ingest run --rm ingest`。既存コレクション/インデックスを削除して全量再構築するため、差分ファイルだけでは実行しない。案1は完了後に `docker compose restart chainlit-app`。案1b: `Workspace > Knowledge` 画面で文書を追加・削除 |
| ログ確認 | `docker compose logs -f <service>` |
| 停止 / 再開 | `docker compose down` / `docker compose up -d`(volume は保持される) |
| アプリ更新 | ソース修正 → `docker compose up -d --build` |
| バックアップ | volume を停止中にアーカイブ: `docker run --rm -v plan2_qdrant-data:/from -v $(pwd):/to alpine tar czf /to/qdrant-backup.tgz -C /from .`(対象: 案1 `chroma-data` / 案1b `open-webui-data` / 案2 `qdrant-data`, `open-webui-data` / 案3 `opensearch-data`, `pg-data`, `open-webui-data`) |

## 5. トラブルシューティング

| 症状 | 原因と対処 |
|---|---|
| rag-api が 503「コレクション/インデックスがありません」 | ingest 未実行。§1〜3 の取り込み手順を実行する |
| TEI が起動直後に応答しない | 初回のモデルダウンロード中。`docker compose logs tei-embed` で進捗確認(volume `hf-cache` にキャッシュされ 2 回目以降は速い) |
| OpenSearch が起動ループ | `vm.max_map_count` 未設定(§3-1)、またはヒープ過大。`docker compose logs opensearch` を確認 |
| 回答が「資料からは回答できません」ばかり | ①ingest 済みか ②`RERANK_THRESHOLD` が高すぎないか(0 にして切り分け)③質問が文書内容と合っているか、を順に確認 |
| vLLM への接続エラー | 案1b は Open WebUI から vLLM へ直結し、案1/2/3 は各アプリから接続する。`.env` の `VLLM_BASE_URL` と §0-2 の疎通を確認(コンテナ内からは `localhost` は使えない — Node A の実ホスト名/IP を指定する) |
| Embedding モデルを変えたら検索が壊れた | ベクトル空間の互換性はない。`documents/` の全コーパスを確認して通常の取り込みコマンドで全量再構築する(案3 は `.env` の `EMBED_DIM` も合わせる) |
| e5 系モデルで精度が悪い | 案1 は `common.py` が prefix を自動付与。案1b は自動付与がないため bge-m3 を推奨。案2/3 の TEI 構成で e5 系を使う場合は query:/passage: の付与処理を追加する必要がある(既定の bge-m3 は不要) |

## 6. 動作確認チェックリスト(受け入れ)

1. WebUI にアクセスでき、モデル(`knowledge-rag` / 案1 は Chainlit 画面 / 案1b は vLLM のモデルを直接選択)が使える
2. 投入した文書の内容を質問すると、本文に基づいた回答 + 参考資料(ファイル名)が返る
3. 文書に存在しない事柄を質問すると「資料からは回答できません」と返る(捏造しない)
4. `docker compose restart` 後もインデックスと(案1b/2/3)会話履歴が保持されている
5. 以降の精度評価は [evaluation-spec.md](evaluation-spec.md) の手順で実施する
