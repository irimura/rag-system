# 案1(Chroma)コーパス取り込み

> 以降のコマンド例中の `${repo_dir}` は、実行前にリポジトリの絶対パスへ置き換えてください。

## 前提

- [事前準備](prerequisites.md) と [ダウンロード手順](download.md) を完了している
- [Node B構築手順](../03-deployment/README.md) §1に従い `03-deployment/plan1/.env` を作成済み
- `documents/` 直下には置かず、`laws` / `whitepaper` / `ipa` / `livedoor` / `wikipedia` 配下を使う
- `ingest.py` は既存 Chroma コレクションを削除し、`documents/` 全体から毎回再構築する

案1は `group` フィルタを実装していませんが、案2/3への移行と配置ミス防止のため固定グループ構成を使います。

## 段階1(動作確認)

```bash
cd ${repo_dir}
bash 04-corpus/scripts/prepare_stage.sh smoke 1 copy
cd 03-deployment/plan1
docker compose build
docker compose --profile ingest run --rm ingest
docker compose restart chainlit-app
```

配置内容は法令10本 + 情報通信白書1年度分です。ingestログの「文書 N件 -> チャンク N件」と Chroma登録完了を記録します。

## 段階2(精度評価)

```bash
cd ${repo_dir}
bash 04-corpus/scripts/prepare_stage.sh accuracy 1 copy
cd 03-deployment/plan1
docker compose --profile ingest run --rm ingest
docker compose restart chainlit-app
```

`prepare_stage.sh` は段階1の `laws` / `whitepaper` を残し、`ipa` / `livedoor` を追加します。ingestは追加分だけでなく4グループ全量を再登録します。

## 段階3(負荷・規模試験)

```bash
cd ${repo_dir}
bash 04-corpus/scripts/prepare_stage.sh load 1 copy
cd 03-deployment/plan1
docker compose --profile ingest run --rm ingest
docker compose restart chainlit-app
```

案1での Wikipedia 全件は推奨しません。まず記事数上限付きの部分集合で、埋め込み時間、Chroma容量、検索待ち時間、再構築中の Node B負荷を測ります。

次のいずれかに該当したら案2/3への移行を優先します。

- 10万チャンク超で全量再構築が運用時間枠に収まらない
- Chroma、Embedding、Chainlitの同居でメモリ/CPU競合が継続する
- 複数利用者、グループ認可、独立した DB監視/バックアップが必要
- Wikipedia全件または数百万チャンクを扱う

## 検収

取り込みログのチャンク数を保存し、Chroma内部件数を確認します。

```bash
docker compose --profile ingest run --rm --no-deps ingest python -c 'import os; from langchain_chroma import Chroma; db=Chroma(persist_directory=os.getenv("CHROMA_DIR", "/data/chroma_db")); print(db._collection.count())'
docker compose logs --tail 200 chainlit-app
```

次を確認します。

1. 法令の条番号、白書の年度/数値、IPA固有語、livedoorカテゴリ固有語が検索できる
2. 段階2/3の再取り込み後も前段階の文書が検索できる
3. PDF抽出品質の目視不良箇所と検索失敗が対応している
4. `documents/` と Chroma件数、取り込み所要時間、ディスク使用量を記録した

## トラブルシュート

| 症状 | 対処 |
|---|---|
| Chroma削除時に例外 | Chainlitがコレクションを使用中なら `docker compose stop chainlit-app` 後に ingestし、完了後 `docker compose up -d chainlit-app` |
| 再取り込み後に旧結果が見える | ingest完了後の `docker compose restart chainlit-app` と件数を確認 |
| メモリ不足/極端に遅い | Wikipedia記事上限を下げ、`CHUNK_SIZE`、バッチ対象、EBS空き容量を確認。継続するなら案2/3へ移行 |
| PDFだけ検索できない | [ダウンロード手順](download.md)の PDFサンプリングを再実施し、Loader/OCR変更を検討 |
