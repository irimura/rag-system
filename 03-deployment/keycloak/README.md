# 検証用 Keycloak 構築手順

`realm-rag.json` は、外部 IdP の開通とバックチャネル経路整備が完了する前に、OIDC フロー全体(ログイン、`groups` claim、グループ同期)をネットワーク変更なしで先行検証するための realm import です。`open-webui` client の固定 secret と初期パスワードは、隔離された検証環境での露出を前提とした値であり、本番では使用しません。外部 IdP の開通後は compose profile `idp` を起動しません。

- issuer: `http://keycloak:8080/realms/rag`
- client ID: `open-webui`
- client secret: `open-webui-local-verification-secret`
- groups: `dept-a` / `dept-b` / `eval`
- users: alice / bob / carol / eva(初回ログイン時にパスワード変更必須)

案1b/2/3 で HTTPS 経由の OIDC を検証する場合は、起動前に realm の `redirectUris` へ実際の公開ホスト名を使った `https://${node_b_hostname}/oauth/oidc/callback` を明示追加します。Keycloak はホスト位置の wildcard を受け付けません。

本番 IdP では Open WebUI の issuer、client ID/secret、redirect URI、`groups` claim mapper を差し替えます。固定 secret と検証ユーザーを移行しないでください。
