# 検証用 Keycloak OIDC 動作検証手順

この文書は、案1b(Open WebUI 単体構成)で検証用 Keycloak を使い、OIDC ログインと `groups` claim によるグループ同期を確認する手順書です。外部 IdP の開通やバックチャネル経路の整備前に、Node B 内だけで OIDC フローを先行検証できます。

案1b の標準経路は、Nginx へ SSH LocalForward した `https://localhost:8441` です。Keycloak の issuer はブラウザと Open WebUI コンテナの双方で `http://keycloak:8080/realms/rag` に統一します。

| 項目 | 検証値 |
|---|---|
| realm | `rag` |
| issuer | `http://keycloak:8080/realms/rag` |
| client ID | `open-webui` |
| client secret | `open-webui-local-verification-secret` |
| 案1b の redirect URI | `https://localhost:8441/oauth/oidc/callback` |
| デバッグ経路の redirect URI | `http://localhost:3000/oauth/oidc/callback` |
| groups | `dept-a` / `dept-b` / `eval` |
| users | alice / bob / carol / eva |

固定 client secret、検証ユーザー、初期パスワードは隔離された検証環境での露出を前提とした値です。本番では使用しません。

## 1. クライアント(PC)側設定

### 1.1 SSH LocalForward

[AWS 構築手順](../../02-provisioning/aws-provisioning.md)の既存 `ragsys-app-001b` エントリへ、Keycloak とデバッグ用 Open WebUI の LocalForward を追加します。既存の `LocalForward 8441 localhost:443` は削除しません。

```sshconfig
Host ragsys-app-001b
    HostName <app1b-instance-id>
    LocalForward 8441 localhost:443
    LocalForward 8080 127.0.0.1:8180
    LocalForward 3000 127.0.0.1:3000
```

`HostName`、`User`、`IdentityFile`、EICE の `ProxyCommand` 等は AWS 構築手順の既存設定をそのまま使います。設定後、次の接続を検証中は維持します。

```bash
ssh -N ragsys-app-001b
```

- `https://localhost:8441` → Node B の Nginx `443` → Open WebUI
- `http://keycloak:8080` → Node B の `127.0.0.1:8180` → Keycloak `8080`
- `http://localhost:3000` → Node B のデバッグポート `127.0.0.1:3000` → Open WebUI `8080`

本手順では Nginx の標準経路 `https://localhost:8441` を使用します。ポート `3000` は、登録済みのデバッグ用 redirect URI を使って問題を切り分ける場合だけ使用します。

### 1.2 hosts の設定

利用端末の hosts に次の行を追加します。

```text
127.0.0.1 keycloak
```

この設定は必須です。ブラウザは Keycloak の認可画面へアクセスし、Open WebUI コンテナは discovery/token endpoint へ接続します。両者から見える issuer を `http://keycloak:8080` に一致させないと、ID token の `iss` 検証に失敗します。利用端末では `keycloak` を `127.0.0.1` に解決し、SSH LocalForward で Node B の Keycloak へ転送します。コンテナ内では Docker DNS が `keycloak` サービスを直接解決します。

macOS では Terminal から編集し、DNS キャッシュを消去します。

```bash
sudo vim /etc/hosts
sudo dscacheutil -flushcache
sudo killall -HUP mDNSResponder
```

Windows では「メモ帳」を右クリックして「管理者として実行」し、`C:\Windows\System32\drivers\etc\hosts` を開いて追記します。ファイル選択画面では表示対象を「すべてのファイル」に変更してください。保存後、管理者権限の PowerShell またはコマンドプロンプトで次を実行します。

```powershell
ipconfig /flushdns
```

SSH 接続と §3.1 の Keycloak 起動後、ブラウザで `http://keycloak:8080/realms/rag/.well-known/openid-configuration` を開き、JSON の `issuer` が `http://keycloak:8080/realms/rag` であることを確認します。

## 2. Open WebUI 側設定

### 2.1 OIDC 設定の有効化

Node B で案1b の `.env` を編集します。`.env.example` のコメントアウト済み OIDC ブロックを、次の値で有効化します。

```bash
cd 03-deployment/plan1b
vim .env
```

```dotenv
ENABLE_OAUTH_SIGNUP=true
OAUTH_CLIENT_ID=open-webui
OAUTH_CLIENT_SECRET=open-webui-local-verification-secret
OPENID_PROVIDER_URL=http://keycloak:8080/realms/rag/.well-known/openid-configuration
OPENID_REDIRECT_URI=https://localhost:8441/oauth/oidc/callback
OAUTH_PROVIDER_NAME=Keycloak
ENABLE_OAUTH_GROUP_MANAGEMENT=true
ENABLE_OAUTH_GROUP_CREATION=true
OAUTH_GROUP_CLAIM=groups
```

| 変数 | 意味 |
|---|---|
| `ENABLE_OAUTH_SIGNUP` | OIDC で認証した未登録ユーザーを Open WebUI に作成します。 |
| `OAUTH_CLIENT_ID` | Keycloak に登録した client ID を指定します。 |
| `OAUTH_CLIENT_SECRET` | confidential client の認証に使う secret を指定します。 |
| `OPENID_PROVIDER_URL` | realm `rag` の OpenID Connect discovery endpoint を指定します。 |
| `OPENID_REDIRECT_URI` | Open WebUI が Keycloak へ送る callback URL を明示し、ブラウザの入口と一致させます。 |
| `OAUTH_PROVIDER_NAME` | ログイン画面の「Keycloak で続行」に使うプロバイダー名です。 |
| `ENABLE_OAUTH_GROUP_MANAGEMENT` | OIDC claim を正としてユーザーのグループ所属を同期します。 |
| `ENABLE_OAUTH_GROUP_CREATION` | claim に含まれる未作成グループを Open WebUI に自動作成します。 |
| `OAUTH_GROUP_CLAIM` | グループ一覧を読む claim 名として `groups` を指定します。 |

OAuth 設定は PersistentConfig の対象です。初回起動後に環境変数を変更した場合、管理画面や DB に保存済みの値が優先されることがあります。まずコンテナを再作成し、反映されない場合は管理者設定の OAuth 値も確認します。

```bash
docker compose up -d --force-recreate open-webui
docker compose logs -f open-webui
```

### 2.2 ログイン画面とグループ同期の確認

ブラウザで `https://localhost:8441` を開きます。自己署名証明書を使用している場合は、検証環境であることを確認して警告を承認します。ログイン画面に「Keycloak で続行」ボタンが表示されることを確認してください。

`realm-rag.json` の mapper type は `oidc-group-membership-mapper`、claim 名は `groups`、`full.path=false` です。このため `/dept-a` は `dept-a` として token に入り、Open WebUI でも `dept-a` グループとして扱われます。

`ENABLE_OAUTH_GROUP_MANAGEMENT=true` と `ENABLE_OAUTH_GROUP_CREATION=true` により、ログイン時に `groups` claim の値と同名のグループが自動作成され、ユーザー所属が同期されます。Open WebUI の管理者で「管理者パネル」→「グループ」を開いてグループを確認し、「管理者パネル」→「ユーザー」で対象ユーザーの所属を確認します。同期後は Keycloak 側の所属が正となり、Open WebUI 側だけで変更した所属は次回ログイン時に上書きされます。

## 3. Keycloak 側設定

### 3.1 起動と管理コンソールへのログイン

Node B で Keycloak を起動します。

```bash
cd 03-deployment/plan1b
docker compose --profile idp up -d keycloak
docker compose logs -f keycloak
```

ブラウザで `http://keycloak:8080` を開き、「Administration Console」からログインします。管理者の入力値は `.env` の `KEYCLOAK_ADMIN_USERNAME` / `KEYCLOAK_ADMIN_PASSWORD` です。compose がこれらをコンテナ内の `KC_BOOTSTRAP_ADMIN_USERNAME` / `KC_BOOTSTRAP_ADMIN_PASSWORD` へ渡します。ログイン後、画面左上の realm 選択で `rag` を選びます。

### 3.2 検証ユーザーでのログイン

| ユーザー | 初期パスワード | 初期グループ |
|---|---|---|
| alice | `change-me-alice` | `dept-a` |
| bob | `change-me-bob` | `dept-b` |
| carol | `change-me-carol` | `dept-a`、`dept-b` |
| eva | `change-me-eva` | `eval` |

Open WebUI の「Keycloak で続行」を押し、上表のユーザー名と初期パスワードでログインします。初期パスワードは `temporary=true` のため、初回ログイン時に「Update password」が表示されます。新しい検証用パスワードを2回入力して確定すると、Open WebUI の callback へ戻ります。変更後は初期パスワードではログインできません。

別ユーザーを試すときは Open WebUI と Keycloak からログアウトするか、ブラウザのプライベートウィンドウを使います。

### 3.3 ユーザー・グループ・所属の変更

管理コンソールで realm `rag` を選んだうえで、次の操作を行います。Keycloak の画面言語によってメニューは英語表示です。

- ユーザー追加: 「Users」→「Add user」で username、email 等を保存し、「Credentials」→「Set password」でパスワードと Temporary の有無を設定します。
- グループ追加: 「Groups」→「Create group」でグループ名を保存します。
- 所属変更: 「Users」→対象ユーザー→「Groups」→「Join Group」で追加します。解除は所属一覧から対象グループを選んで「Leave」を実行します。

変更後、そのユーザーで Open WebUI へログインし直して同期を確認します。

### 3.4 redirect URI を変更する場合

案1b の正典は `https://localhost:8441/oauth/oidc/callback` です。デバッグポートへ直接アクセスする場合は、`.env` の `OPENID_REDIRECT_URI` を `http://localhost:3000/oauth/oidc/callback` に変更します。ブラウザの入口、`OPENID_REDIRECT_URI`、Keycloak の登録値は、scheme、host、port、path を完全一致させてください。

HTTPS 公開名で検証する場合は、管理コンソールで realm `rag` →「Clients」→ `open-webui` →「Settings」→「Valid redirect URIs」へ、たとえば `https://${node_b_hostname}/oauth/oidc/callback` を追加します。対応する TLS 証明書とクライアント側の名前解決も必要です。Keycloak はホスト部分の wildcard をサポートしないため、具体的なホスト名を登録します。

## 4. 検証シナリオとトラブルシュート

### 4.1 検証シナリオ

1. 管理者で Open WebUI にログインし、「管理者パネル」→「グループ」と「ユーザー」を開けることを確認します。
2. 別のブラウザセッションで「Keycloak で続行」を押し、alice で初回ログインとパスワード変更を完了します。
3. 管理者セッションで `dept-a` グループが自動作成され、alice が所属していることを確認します。
4. carol でログインし、同じユーザーに `dept-a` と `dept-b` の2グループが同時に反映されることを確認します。
5. eva でログインし、`eval` グループが作成されて eva が所属することを確認します。
6. 必要に応じて bob でもログインし、`dept-b` だけが反映されることを確認します。

### 4.2 トラブルシュート

| 症状 | 主な原因 | 対処 |
|---|---|---|
| Keycloak 画面は開くが callback 後に issuer 検証で失敗する | hosts 未設定、またはブラウザとコンテナで issuer のホスト名が異なる | hosts の `127.0.0.1 keycloak`、SSH の `8080 → 8180`、discovery JSON の `issuer` を確認します。 |
| Keycloak に `Invalid parameter: redirect_uri` または `redirect_uri mismatch` と表示される | `https://localhost:8441` 以外から開始した、または `OPENID_REDIRECT_URI` と Keycloak 登録値が不一致 | ブラウザを `https://localhost:8441` で開き、両方を `https://localhost:8441/oauth/oidc/callback` に揃えます。 |
| discovery endpoint または Keycloak 管理画面を開けない | SSH LocalForward 未接続、Keycloak 未起動、またはローカル 8080 が競合 | `ssh -N ragsys-app-001b`、`docker compose ps keycloak`、`docker compose logs keycloak` を確認します。 |
| Open WebUI ログに discovery endpoint への接続失敗が出る | Keycloak 未起動、または Open WebUI と Keycloak が同じ compose network にいない | profile `idp` で Keycloak を起動し、案1b の compose プロジェクト内で両サービスが稼働していることを確認します。 |
| 「Keycloak で続行」が表示されない | OIDC 環境変数が未反映、または PersistentConfig の保存値が優先 | `.env` を確認して Open WebUI を `--force-recreate` し、管理者設定の OAuth 保存値も確認します。 |
| ログインできるがグループが作成・同期されない | group 管理・作成が無効、claim 名不一致、または古いセッション | 3つのグループ関連変数を確認し、Keycloak からもログアウトして再ログインします。token の claim 名は `groups` です。 |

本番の外部 IdP 利用時は profile `idp` を起動しません。本番移行時は issuer/discovery URL、client ID、client secret、redirect URI、group claim の写像を組織 IdP の値へ差し替え、検証用 secret、ユーザー、初期パスワードは移行しないでください。
