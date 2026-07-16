# 案2(Qdrant + TEI)コーパス取り込み

> 以降のコマンド例中の `${repo_dir}` は、実行前にリポジトリの絶対パスへ置き換えてください。所要時間は Node B、EBS、TEIモデル、チャンク設定で変動するため、初回実測で更新してください。

## 前提

- [事前準備](prerequisites.md) と [ダウンロード手順](download.md) を完了している
- [Node B構築手順](../deployment-guide.md) §2に従い `.env`、TLS証明書、`auth/groups.json` を準備済み
- `groups.json` に固定5グループと検証ユーザーの所属を登録済み
- TEI Embed、Qdrant、rag-apiが起動し、health/readyzが成功する
- ingestは `force_recreate=True` で単一 collectionを削除・再作成する

各段階は累積配置 + 全量再取り込みです。差分ファイルだけを `documents/` に置いて実行すると、前段階の文書が消えるため禁止します。

## 段階1(動作確認)

```bash
cd ${repo_dir}/deploy/plan2
vim .env
vim auth/groups.json
cd ${repo_dir}
bash scripts/corpus/prepare_stage.sh smoke 2 copy
cd deploy/plan2
docker compose up -d --build
curl http://localhost:8081/health && curl http://localhost:6333/readyz && curl http://localhost:8000/health
docker compose --profile ingest run --rm ingest
```

## 段階2(精度評価)

```bash
cd ${repo_dir}
bash scripts/corpus/prepare_stage.sh accuracy 2 copy
cd deploy/plan2
docker compose --profile ingest run --rm ingest
```

`laws` / `whitepaper` を残したまま `ipa` / `livedoor` を追加し、4グループ全量を同じ collectionへ再登録します。グループ別チャンク数が ingestログに出ることを確認します。

## 段階3(負荷・規模試験)

```bash
cd ${repo_dir}
bash scripts/corpus/prepare_stage.sh load 2 symlink
cd deploy/plan2
docker compose --profile ingest run --rm ingest
```

最初は Wikipedia部分集合から開始し、記事数を段階的に増やします。全件実施前に EBS拡張、バックアップ、再構築時間枠、TEI CPU使用率、Qdrant容量を確認します。

| 段階 | 所要時間の初期計画値 | 追加空き容量の初期計画値 |
|---|---:|---:|
| 動作確認 | 10〜60分 | 10GB以上 |
| 精度評価 | 1〜6時間 | 30〜50GB以上 |
| 負荷・規模試験(部分) | 6〜24時間 | 100GB以上 |
| 負荷・規模試験(全件) | 1日〜複数日 | 300〜500GB以上 |

この表は保証値ではありません。ingestログのチャンク進捗と `time` の実測を次回見積もりに使います。

## 検収

`.env` を読み込み、Qdrant APIで正確なポイント数を取得します。

```bash
set -a && source .env && set +a
curl --fail -sS -X POST http://localhost:6333/collections/${QDRANT_COLLECTION}/points/count -H 'Content-Type: application/json' -d '{"exact":true}' | python3 -m json.tool
docker compose logs --tail 200 rag-api
```

次を確認します。

1. APIの `count` が ingestログの総チャンク数と一致する
2. グループ別チャンク数の合計が総チャンク数と一致する
3. `EVAL_TOKEN` では全グループ、単一グループ利用者では所属文書だけが検索される
4. 段階2/3後も前段階の文書が検索できる
5. 所要時間、Qdrant volume、HF cache、`documents/` の容量を記録する

## トラブルシュート

| 症状 | 対処 |
|---|---|
| collectionが空/存在しない | TEI health、Qdrant readyz、ingest終了コード、`QDRANT_COLLECTION` を確認 |
| 途中失敗後に件数が少ない | collectionは再作成済みの可能性がある。原因修正後、累積 `documents/` を確認して ingestを最初から再実行 |
| 403または0件 | `groups.json` の固定グループ、利用者所属、`documents/<group>/` の第1階層を確認 |
| TEIが遅い/停止 | CPU/RAM、モデルキャッシュ、コンテナログを確認し、Wikipedia記事数を下げて再計測 |
| ディスク不足 | symlink配置へ切り替え、EBSを拡張し、raw/processed/Qdrantのピークを再見積もり |
