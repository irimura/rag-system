# 案1b(Open WebUI)コーパス取り込み

> 以降のコマンド例中の `${repo_dir}`、`${open_webui_url}`、`${api_key}`、`${knowledge_id}`、`${file}` は、実行前に環境の値へ置き換えてください。

## 前提

- [Node B構築手順](../03-deployment/README.md) §1bに従い Open WebUI v0.9.6を起動済み
- 案1bには `documents/` と `ingest.py` がないため、`prepare_stage.sh` は使用しない
- Admin Panelで `laws` / `whitepaper` / `ipa` / `livedoor` / `wikipedia` のグループを作成する
- Workspace > Knowledgeで同名の private Knowledgeを作成し、対応グループへ read権限を付与する
- APIキーはアップロード専用ユーザーで発行し、対象 Knowledgeへの権限だけを与える

案1bは案1/2/3の全量再構築方式とは異なり、Open WebUIがファイル単位で処理します。段階進行では既存 Knowledgeを残して追加します。削除/差し替え時は Knowledge内の旧ファイルを明示的に削除してから再アップロードします。

## 段階1(動作確認)

### UI

1. Workspace > Knowledgeで `laws` と `whitepaper` を作成する
2. `${CORPUS_DIR}/processed/laws/` の10 Markdownを `laws` へアップロードする
3. `${CORPUS_DIR}/raw/whitepaper/` の PDFを `whitepaper` へアップロードする
4. 各 Knowledgeを privateにし、同名グループへ read権限を付与する
5. 管理者ではない検証ユーザーで、許可Knowledgeだけが表示・検索されることを確認する

### API

Knowledgeは UIで作成し、ブラウザURL末尾の UUIDを `${knowledge_id}` とします。ファイルをアップロードし、返却されたIDを保存します。

```bash
file_id="$(curl --fail -sS -X POST ${open_webui_url}/api/v1/files/ -H "Authorization: Bearer ${api_key}" -H 'Accept: application/json' -F "file=@${file}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
```

非同期処理の状態が `completed` になるまで繰り返し確認します。

```bash
curl --fail -sS ${open_webui_url}/api/v1/files/${file_id}/process/status -H "Authorization: Bearer ${api_key}" | python3 -m json.tool
```

完了後に Knowledgeへ追加します。

```bash
curl --fail -sS -X POST ${open_webui_url}/api/v1/knowledge/${knowledge_id}/file/add -H "Authorization: Bearer ${api_key}" -H 'Content-Type: application/json' -d "{\"file_id\":\"${file_id}\"}" | python3 -m json.tool
```

Open WebUI v0.9.6では `POST /api/v1/files/` の metadataに `knowledge_id` を渡す単一呼び出しも利用できますが、疎通確認では処理状態と追加結果を分けて観測できる上記手順を使用します。

## 段階2(精度評価)

### UI

`ipa` と `livedoor` Knowledgeを追加します。IPA PDFは少数なので UIアップロードが現実的です。livedoorは7,367件あるため、カテゴリ単位で分割し、同時に大量選択せず、処理完了とディスク増加を確認しながら投入します。

### API

上記3コマンドをファイルごとに実行します。まず各カテゴリ10〜100件で疎通確認し、その後にバッチを増やします。失敗したファイルID、処理状態、再実行結果を記録し、同じ原文を重複登録しないよう Knowledge内のファイル一覧を確認します。

livedoor本文は改変・要約保存せず、社内評価用途に限定します。Open WebUI内部の抽出テキスト、チャンク、エクスポートを再配布しません。

## 段階3(負荷・規模試験)

案1bは数十万チャンク以上の負荷・規模試験の対象外です。ブラウザ/APIで大量ファイルを管理し、Open WebUI内蔵 Chromaとアプリを同居させる構成は、本リポジトリの段階3の再現性、監視、全量再構築、件数検収に適しません。

Wikipediaを使う負荷試験は [案2](ingest-plan2.md) または [案3](ingest-plan3.md) へ移行します。

## 検収

1. Knowledgeごとのファイル数と処理失敗数を記録する
2. APIアップロードは `process/status=completed` を確認する
3. `laws` 利用者から `livedoor` Knowledgeが見えない等、private Knowledge ACLを一般ユーザーで確認する
4. 法令条番号、白書年度、IPA固有語、livedoorカテゴリ固有語で検索する
5. PDF抽出品質を [ダウンロード手順](download.md) に従って目視する

## トラブルシュート

| 症状 | 対処 |
|---|---|
| Knowledge追加時に `empty content` | ファイル処理が未完了。`GET /api/v1/files/${file_id}/process/status` が `completed` になるまで待つ |
| APIが401/403 | APIキー所有者のロール、Knowledge権限、URL、キー失効を確認 |
| livedoor投入が終わらない | カテゴリ/件数を小分けにし、同時投入を減らす。大規模化が目的なら案2/3へ移行 |
| 所属外Knowledgeが見える | Knowledgeを privateにし、グループ read権限と検証ユーザー所属を再確認。adminはACL受け入れ試験に使わない |
