# 検証用 Keycloak

`realm-rag.json` は OIDC とグループ同期をローカル検証するための realm import です。`open-webui` client の固定 secret と初期パスワードは、隔離された検証環境での露出を前提とした値であり、本番では使用しません。

- issuer: `http://keycloak:8080/realms/rag`
- client ID: `open-webui`
- client secret: `open-webui-local-verification-secret`
- groups: `dept-a` / `dept-b` / `eval`
- users: alice / bob / carol / eva(初回ログイン時にパスワード変更必須)

本番 IdP では Open WebUI の issuer、client ID/secret、redirect URI、`groups` claim mapper を差し替えます。固定 secret と検証ユーザーを移行しないでください。
