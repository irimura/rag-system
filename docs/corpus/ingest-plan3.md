# 案3(OpenSearch)コーパス取り込み

> 以降のコマンド例中の `${repo_dir}` は、実行前にリポジトリの絶対パスへ置き換えてください。所要時間は Node B、EBS、TEIモデル、チャンク設定で変動します。

## 前提

- [事前準備](prerequisites.md) と [ダウンロード手順](download.md) を完了している
- [Node B構築手順](../deployment-guide.md) §3の Security Plugin有効手順を完了している
- `vm.max_map_count=262144`、`.env`、TLS証明書、`auth/groups.json` を準備済み
- 固定5グループを `groups.json` に登録し、`security-init` がグループ別 DLS role/internal userを作成できる
- OpenSearch起動後に同じコンテナから `root-ca.pem` を取得し、`rag-api` / `security-init` / `ingest` へ read-only mountしている
- `node-0.example.com` の Docker aliasとデモ証明書SANを維持し、`rag-api` / `ingest` は CA/ホスト名を検証する

N-01/N-02で確定した順序は、OpenSearchだけ起動 → CA抽出 → 全イメージbuild → 全サービス起動 → `security-init` 終了コード0確認です。`rag-api` と ingestへ初期管理者パスワードを渡しません。

ingestは既存 indexを削除し、mappingを再作成して、TEI埋め込みを32チャンク単位で bulk登録します。各段階は累積配置 + 全量再取り込みです。

## 段階1(動作確認)

```bash
cd ${repo_dir}/deploy/plan3
sudo sysctl -w vm.max_map_count=262144
vim .env
vim auth/groups.json
docker compose up -d --build opensearch
docker compose logs -f opensearch
mkdir -v -p rag-api/certs
docker compose cp opensearch:/usr/share/opensearch/config/root-ca.pem rag-api/certs/root-ca.pem
docker compose build
docker compose up -d
docker compose ps -a security-init
docker compose logs security-init
cd ${repo_dir}
bash scripts/corpus/prepare_stage.sh smoke 3 copy
cd deploy/plan3
docker compose --profile ingest run --rm ingest
```

OpenSearchログの started確認後に `docker compose logs -f` を Ctrl-Cで終了します。CA抽出前に残りのサービスを起動しません。

## 段階2(精度評価)

```bash
cd ${repo_dir}
bash scripts/corpus/prepare_stage.sh accuracy 3 copy
cd deploy/plan3
docker compose --profile ingest run --rm ingest
```

4グループ全量から indexを再作成し、BM25用 `text`、ベクトル、`source`、`group` を同時登録します。

## 段階3(負荷・規模試験)

```bash
cd ${repo_dir}
bash scripts/corpus/prepare_stage.sh load 3 symlink
cd deploy/plan3
docker compose --profile ingest run --rm ingest
```

Wikipedia部分集合で bulk速度、refresh時間、segment/heap、ディスク増加を測ってから全件へ進みます。再構築中は indexを一度削除するため、同じ indexを検索する利用者には停止時間が発生します。本番相当では別 indexへ構築して alias切替する改善を別途設計しますが、現行サンプルは単一 index全量再構築です。

| 段階 | 所要時間の初期計画値 | 追加空き容量の初期計画値 |
|---|---:|---:|
| 動作確認 | 10〜60分 | 15GB以上 |
| 精度評価 | 1〜6時間 | 40〜60GB以上 |
| 負荷・規模試験(部分) | 6〜24時間 | 120GB以上 |
| 負荷・規模試験(全件) | 1日〜複数日 | 300〜500GB以上 |

## 検収

`.env` を読み込み、CAと検索専用ユーザーで index件数を確認します。

```bash
set -a && source .env && set +a
curl --fail -sS --cacert rag-api/certs/root-ca.pem --resolve node-0.example.com:9200:127.0.0.1 -u "rag_api:${OS_RAG_PASSWORD}" https://node-0.example.com:9200/${OS_INDEX}/_count | python3 -m json.tool
curl --fail -sS --cacert rag-api/certs/root-ca.pem --resolve node-0.example.com:9200:127.0.0.1 -u "rag_api:${OS_RAG_PASSWORD}" https://node-0.example.com:9200/_cluster/health | python3 -m json.tool
```

次を確認します。

1. `_count` が ingestログの総チャンク数と一致する
2. `group` ごとの件数を aggregationで確認し、ログのグループ別チャンク数と一致する
3. `rag_api` では読み取り成功、更新操作は403になる
4. グループ別 internal userの DLSで所属外 `group` が0件になる
5. BM25、ベクトル、RRF、rerankの検索が段階別代表質問で成功する
6. index容量、heap、bulk所要時間、失敗/retry件数を記録する

グループ別件数の確認例です。

```bash
curl --fail -sS --cacert rag-api/certs/root-ca.pem --resolve node-0.example.com:9200:127.0.0.1 -u "rag_api:${OS_RAG_PASSWORD}" https://node-0.example.com:9200/${OS_INDEX}/_search -H 'Content-Type: application/json' -d '{"size":0,"aggs":{"groups":{"terms":{"field":"group","size":10}}}}' | python3 -m json.tool
```

## トラブルシュート

| 症状 | 対処 |
|---|---|
| CAファイルがない | OpenSearchを先に起動し、同じコンテナから `root-ca.pem` を再取得。イメージbuild時の COPYへ戻さない |
| hostname verification失敗 | `OPENSEARCH_URL=https://node-0.example.com:9200`、Docker alias、CA mountを確認 |
| `indices.exists()` が403 | `rag_reader` に `indices:admin/get` があることを確認。存在確認用に未定義の `indices:admin/exists` を追加しない |
| ingestがindex削除後に停止 | 累積 `documents/`、TEI health、ingestユーザー資格情報を確認し、全量を最初から再実行 |
| bulkが遅い/429 | heap、CPU、EBS IOPS、segment、TEI速度を確認し、Wikipedia件数を下げて再計測 |
| DLS越境 | `groups.json`、security-initログ、group field mapping、グループ別user/roleを確認し、修正後に全量再取り込み |
