# Node B デプロイ手順(全案)

[03-deployment/](./) 配下の Dockerfile / docker-compose.yml / パラメータファイルを使って、アプリ+データノード(Node B)を構築する手順です。

| 案 | 構築ファイル | 公開ポート | 主なパラメータファイル |
|---|---|---|---|
| 案1 | [03-deployment/plan1/](plan1/) | 8000(Chainlit) | `.env` |
| 案1b | [03-deployment/plan1b/](plan1b/) | 80/443(Nginx) | `.env`、`nginx/conf.d/rag.conf` |
| 案2 | [03-deployment/plan2/](plan2/) | 80/443(Nginx) | `.env`、`nginx/conf.d/rag.conf` |
| 案3 | [03-deployment/plan3/](plan3/) | 80/443(Nginx) | `.env`、`nginx/conf.d/rag.conf`、`opensearch/index-mapping.json` |

> デバッグ用ポート(Open WebUI 3000、Qdrant 6333、TEI 8081/8082、rag-api 8000、OpenSearch 9200)は `127.0.0.1` バインドで外部非公開。Node A(vLLM)には一切手を入れません。

> 検証フェーズのコンテナタグと Python requirements はマイナー系列以上を明示して固定済みです。再検証なしに `latest` / `main` へ戻さないでください。digest 固定を含む最終更新方針は運用設計フェーズで決定します。

> 以降のコマンド例中の `${node_a}` `${node_b}` `${node_b_ip}` `${node_b_hostname}` `${vllm_api_key}` `${repo_url}` `${n}`(構築する案番号 1/2/3)は、実行前に環境に応じた値に置き換えてください。

## 0. 前提条件

- Node B: Ubuntu Server 24.04 LTS(RAM 目安 — 案1/案1b: 8GB〜 / 案2: 16GB〜 / 案3: 32GB〜)。AWS EC2 で構築する場合の Instance Type / AMI 選定は [node-specs.md](../01-design/node-specs.md) を参照
- Node A で vLLM が **OpenAI 互換エンドポイントとしてサービス化済み**で、Node B から HTTP 到達できること(未了の場合は先に [02-provisioning/node-a/](../02-provisioning/node-a/) の compose または systemd unit で `vllm serve` を起動する。スペック・AMI は [node-specs.md](../01-design/node-specs.md) §1)
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
# サービス化(02-provisioning/node-a/)と FW(8080/tcp が Node B から許可)を確認する
```

### 0.3 リポジトリの配置と共通設定

```bash
git clone ${repo_url} && cd rag-system/03-deployment/plan${n}
cp -v .env.example .env
vim .env    # 最低限 VLLM_BASE_URL / VLLM_API_KEY(案1/2/3 は VLLM_MODEL も)を実環境に合わせる
            # 案1b/2/3 は WEBUI_SECRET_KEY を変更。案3は加えて
            # OPENSEARCH_INITIAL_ADMIN_PASSWORD / OS_RAG_PASSWORD /
            # OS_INGEST_PASSWORD / POSTGRES_PASSWORD も別々の値へ変更:
            #   openssl rand -hex 32
```

取り込みたい文書(PDF / Markdown / テキスト)を `documents/` に配置します。

段階別コーパスの取得・前処理・固定グループへの配置・全量再取り込み・検収は [コーパス取り込み手順](../04-corpus/README.md) を参照してください。案1bの UI/API アップロード手順も同書にまとめています。

案1b/2/3 では `.env` のシークレットをすべて別々に `openssl rand -hex 32` で生成します。案2/3 は `FORWARD_USER_INFO_HEADER_JWT_SECRET` と `EVAL_TOKEN`、案3はさらに `OS_GROUP_USER_SECRET` と `KEYCLOAK_DB_PASSWORD` が必要です。

案2/3 では次を実行します。案1bのグループは Open WebUI の Admin Panel で管理するため `groups.json` は使用しません。

```bash
cp -v auth/groups.example.json auth/groups.json
```

案2/3の文書は `documents/<group>/...` に配置します。第1階層(`dept-a` / `dept-b` / `eval`)をチャンクの `group` とし、直下ファイルがある場合は取り込みを fail closed で中止します。

---

## 1. 案1 の構築(Chainlit 単一コンテナ)

```bash
cd 03-deployment/plan1

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
cd 03-deployment/plan1b

# 1) Nginx の TLS 証明書を配置(検証用は自己署名。本番は社内 CA / Let's Encrypt)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout nginx/certs/server.key -out nginx/certs/server.crt -subj "/CN=${node_b_hostname}"

# 2) カスタム Open WebUI のビルドと起動
# Sentence Transformers の tqdm 表示を、処理種別・ID・所要時間付きログへ置き換える
# 初回は Open WebUI と embedding/rerank モデルをダウンロードする
docker compose up -d --build

# 3) 確認
docker compose logs -f open-webui
docker compose ps
```

質問時は、embedding と rerank の各呼び出しについて次の形式で開始・終了が記録されます。同じ `id` の行を対応付けることで、並列実行時も処理種別と所要時間を判別できます。Sentence Transformers の `Batches` プログレスバーは表示されません。

```text
RAG_BATCH_START id=emb-0123456789ab type=embedding items=1 batch_size=1 batches=1
RAG_BATCH_END id=emb-0123456789ab type=embedding status=success elapsed_ms=234.1
RAG_BATCH_START id=rerank-abcdef012345 type=rerank items=9 batch_size=32 batches=1
RAG_BATCH_END id=rerank-abcdef012345 type=rerank status=success elapsed_ms=918.6
```

ブラウザで `https://${node_b}/` を開き(自己署名の場合は警告を承認)、最初のアカウントを管理者として登録します。管理者設定の OpenAI API 接続で Node A の vLLM モデルが表示され、直接選択できることを確認します。

`Workspace > Knowledge` で文書をアップロードし、チャットでその Knowledge を参照して質問します。回答と出典が表示されれば、内蔵 RAG の取り込み・検索・生成経路を確認できています。

グループを Admin Panel で作成し、Knowledge を private に設定して対象グループへ read 権限を付与します。一般ユーザーで所属外 Knowledge が表示・検索されないことを確認します。admin は root 相当のため ACL の受け入れ確認には使用しません。

## 2. 案2 の構築(Open WebUI + Qdrant + TEI)

```bash
cd 03-deployment/plan2

# 1) Nginx の TLS 証明書を配置(検証用は自己署名。本番は社内 CA / Let's Encrypt)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout nginx/certs/server.key -out nginx/certs/server.crt -subj "/CN=${node_b_hostname}"

# 2) ビルドと起動(TEI は初回起動時にモデルを自動ダウンロード)
docker compose up -d --build

# 3) 各サービスの起動確認
curl http://localhost:8081/health        # tei-embed  -> 200(モデル DL 完了まで数分待つ)
curl http://localhost:8082/health        # tei-rerank -> 200
curl http://localhost:6333/readyz        # qdrant     -> 200
curl http://localhost:8000/health        # rag-api    -> {"status":"ok"}

# 4) 取り込み
docker compose --profile ingest run --rm ingest

# 5) RAG API の動作確認(Open WebUI を通さず直接)
set -a && source .env && set +a
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer ${EVAL_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"model":"knowledge-rag","messages":[{"role":"user","content":"(文書に関する質問)"}]}'
```

**Open WebUI の初期設定**: `https://${node_b}/` を開き(自己署名の場合は警告を承認)、最初に作成したアカウントが管理者になります。`OPENAI_API_BASE_URL` で rag-api を接続済みのため、モデル一覧に `knowledge-rag`(`.env` の `RAG_MODEL_NAME`)が表示されればそれを選んで会話を開始できます。

## 3. 案3 の構築(Nginx + OpenSearch ハイブリッド + PostgreSQL)

案3は OpenSearch Security Plugin を有効にし、コンテナ間も TLS と Basic 認証で接続します。検証フェーズでは固定済み OpenSearch イメージが初回起動時に配置するデモ CA / 証明書を使用します。OpenSearch の起動後に公開 CA 証明書だけをホストへ取り出し、`rag-api` / `security-init` / `ingest` へ読み取り専用でマウントします。`security-init` が初期管理者で `rag_api`(検索専用)と `ingest`(インデックス更新用)を冪等作成し、その完了後に各サービスが起動します。

```bash
cd 03-deployment/plan3

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
set -a && source .env && set +a
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer ${EVAL_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"model":"knowledge-rag","messages":[{"role":"user","content":"(文書に関する質問)"}]}'
```

ブラウザで `https://${node_b}/` を開き(自己署名の場合は警告を承認)、管理者アカウントを作成して `knowledge-rag` モデルで会話します。会話履歴・ユーザー情報は PostgreSQL に保存されます。

- `.env` の `OS_HEAP` は Node B の RAM に合わせる(RAM の 25〜50%、32GB 以下)
- `rag-api` と `ingest` は初期管理者パスワードを受け取らず、別々のサービスユーザーで CA とホスト名を検証する
- `rag-api/certs/root-ca.pem` は生成物であり Git 管理しない。OpenSearch イメージを変更またはコンテナを再作成した場合は、手順 4 で同じコンテナから CA を再取得する
- デモ CA / 証明書と `node-0.example.com` の Docker 内 DNS alias は検証フェーズ専用。本番では組織 CA でノード証明書を発行し、OpenSearch の `opensearch.yml` と `rag-api` の `OS_CA_CERT` を置き換える
- Security Plugin 無効時に作成した既存 volume を引き継ぐ場合は、必要データを退避し、全コーパスから再取り込みできることを確認してから `opensearch-data` を新規作成する。初期管理者パスワードは初回初期化時にのみ反映される

## 3.1 認証・グループ越境の確認(案2/3)

コマンド例の `${dept_a_jwt}` と `${rag_dept_a_password}` は、実行前に検証環境の値へ置き換えてください。

```bash
# 認証なしは 401
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/v1/chat/completions -H "Content-Type: application/json" -d '{"model":"knowledge-rag","messages":[{"role":"user","content":"質問"}]}'

# EVAL_TOKEN は全グループを取得可能
set -a && source .env && set +a
curl http://localhost:8000/internal/evaluation/retrieve -H "Authorization: Bearer ${EVAL_TOKEN}" -H "Content-Type: application/json" -d '{"question":"質問","groups":["dept-a","dept-b"]}'

# 案2: dept-a principal で dept-b 文書が返らない
curl http://localhost:8000/internal/evaluation/retrieve -H "X-OpenWebUI-User-Jwt: ${dept_a_jwt}" -H "Content-Type: application/json" -d '{"question":"dept-b 固有語"}'

# 案3: DLS user の直接検索でも dept-b が 0 件
curl --cacert rag-api/certs/root-ca.pem --resolve node-0.example.com:9200:127.0.0.1 -u "rag_dept-a:${rag_dept_a_password}" https://node-0.example.com:9200/knowledge/_search -H "Content-Type: application/json" -d '{"query":{"term":{"group":"dept-b"}}}'
```

案3の最後の応答は `hits.total.value=0` を確認します。パスワードは rag-api コンテナ内の `derive_group_password("dept-a")` と同じ導出値です。

## 3.2 Keycloak(検証用 IdP・任意)

既定はローカル認証だけで完結します。外部 IdP の開通と §3.3 のバックチャネル経路整備が完了する前に、OIDC フロー全体を先行検証するときだけ profile `idp` を起動します。本番の外部 IdP 利用時は起動しません。

```bash
cd 03-deployment/plan${n}
docker compose --profile idp up -d keycloak
```

利用端末の hosts に `127.0.0.1 keycloak` を登録し、SSH LocalForward でローカル 8080 を Node B の 8180 へ転送します。

```bash
ssh -N -L 8080:127.0.0.1:8180 ragsys-app-00${n}
```

`.env` の OIDC ブロックを有効化し、`OPENID_PROVIDER_URL=http://keycloak:8080/realms/rag/.well-known/openid-configuration`、client ID `open-webui`、検証用固定 secret を設定して Open WebUI を再作成します。alice/bob/carol/eva でログインし、issuer と `groups` claim の同期を確認します。

案1b・案2・案3の HTTPS 公開名で検証する場合は、Keycloak 起動前に `03-deployment/keycloak/realm-rag.json` の `redirectUris` へ `https://${node_b_hostname}/oauth/oidc/callback` を明示追加します。Keycloak はホスト位置の wildcard をサポートしません。

案3の PostgreSQL initdb script は空の `pg-data` を初期化する初回だけ keycloak_app role/DB を作成します。既存 volume には同等の SQL を別途適用します。本番は issuer/client/secret/redirect URI を組織 IdP と安定した HTTPS 名へ差し替え、検証用の secret、ユーザー、初期パスワードは移行しません。

## 3.3 外部 IdP へ接続する場合

先に [AWS 構築手順](../02-provisioning/aws-provisioning.md) §2.3 の NAT Gateway 常設または VPC ピアリングで、Node B から IdP の discovery/token endpoint へ HTTPS 接続できるようにします。IdP には client を作成し、`redirect_uri` として `https://${node_b_hostname}/oauth/oidc/callback` を登録します。

`redirect_uri` のホスト名はブラウザから解決・到達できればよく、パブリック DNS での解決は技術的には不要です。ただし、IdP が公開 FQDN や組織ドメインの所有権検証を要求する場合があるため、申請時に確認します。Nginx の証明書は公開 CA + DNS-01、または利用端末へ CA を配布した社内 CA を本番候補とします。詳細は [OIDC 導入設計](../01-design/auth-oidc.md) §5.1 を参照してください。

`.env` の OIDC ブロックを本番 IdP の発行値で設定します。`IDP_HOST` には discovery endpoint のホスト名、client ID/secret には IdP から払い出された値を設定します。

```dotenv
IDP_HOST=idp.example.com
OIDC_CLIENT_ID=replace-with-issued-client-id
OIDC_CLIENT_SECRET=replace-with-issued-client-secret
ENABLE_OAUTH_SIGNUP=true
OAUTH_CLIENT_ID=${OIDC_CLIENT_ID}
OAUTH_CLIENT_SECRET=${OIDC_CLIENT_SECRET}
OPENID_PROVIDER_URL=https://${IDP_HOST}/.well-known/openid-configuration
OAUTH_PROVIDER_NAME=Corporate-IdP
OAUTH_MERGE_ACCOUNTS_BY_EMAIL=true
ENABLE_OAUTH_GROUP_MANAGEMENT=true
ENABLE_OAUTH_GROUP_CREATION=true
OAUTH_GROUP_CLAIM=groups
```

OAuth 設定は PersistentConfig のため、初回起動後に変更する場合は Admin UI/DB の保存値も確認して Open WebUI を再作成します。別 VPC の IdP が社内 CA 証明書を使う場合は、CA バンドルをコンテナへ読み取り専用で配置し、`SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE` 等を設定してから確認します。

Node B 上で Open WebUI コンテナから discovery endpoint へ到達できることを確認します。HTTP 200 と期待する issuer が表示されることを確認してください。

```bash
docker compose exec open-webui python -c "import json, os, urllib.request; url=os.environ['OPENID_PROVIDER_URL']; data=json.load(urllib.request.urlopen(url, timeout=10)); print(data['issuer'])"
```

次にブラウザで Nginx の HTTPS 公開名を開き、外部 IdP でログインします。Open WebUI にセッションが作成され、`groups` claim が管理画面のグループへ同期されることを確認します。経路整備前に同じ機能を確認する場合は §3.2 の検証用 Keycloak を使用します。

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
| OIDC ログインで discovery/token 取得に失敗 | 既定の隔離構成では Open WebUI から外部 IdP へ到達できない。`docker compose exec open-webui` で §3.3 の discovery 確認を実行し、[AWS 構築手順](../02-provisioning/aws-provisioning.md) §2.3 の NAT/ピアリング、DNS、443 egress、CA バンドルを確認 |
| rag-api が 401 | EVAL_TOKEN または Open WebUI v0.9.6 以降の署名 JWT がない/不正。JWT secret が両サービスで同一か確認 |
| rag-api が 403 | email が groups.json にない、所属が空、または要求 group が所属外。fail closed のため設定を修正する |
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
5. 認証なしの rag-api アクセスが HTTP 401 で拒否される
6. dept-a 利用者の検索に dept-b 文書が含まれず、グループ越境が遮断される
7. (任意) Keycloak OIDC でログインし、グループが同期される
8. 以降の精度評価は [evaluation-spec.md](../05-evaluation/evaluation-spec.md) と [TC11](../05-evaluation/cases/TC11_group_authorization.md) で実施する
