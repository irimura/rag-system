# TC11: グループ越境アクセス拒否 — ケース手順書

| 項目 | 内容 |
|---|---|
| 観点 ID | TC11 |
| 観点 | 認証の欠落と、所属外グループの文書検索を拒否できるか |
| 主な検証対象 | 転送 JWT、グループ解決、Qdrant filter、OpenSearch DLS |
| 使用ケース | dept-a / dept-b に同じ検索語を含む識別可能な文書を1件ずつ配置 |

## 1. 目的

WebUI や rag-api の実装不備により、利用者が所属しないグループのチャンクを取得する越境を検出する。

## 2. 前提条件

- [ ] `documents/dept-a/` と `documents/dept-b/` の文書を全再取り込み済み
- [ ] alice(dept-a)の署名 JWT または同等の principal を取得済み
- [ ] `RAG_EVAL_TOKEN` に rag-api の `EVAL_TOKEN` と同じ値を設定済み

## 3. 実行手順

1. 認証ヘッダーなしで `/v1/chat/completions` を呼ぶ
2. alice の principal で dept-a/dept-b 両方に一致する質問を送る
3. eval token で `/internal/evaluation/retrieve` を呼び、`--groups dept-a dept-b` を指定する
4. 案3では `rag_dept-a` internal user で dept-b 固有語を直接検索する

## 4. 期待結果と判定基準

| # | 確認項目 | 期待結果 | 判定 |
|---|---|---|---|
| 1 | 認証なし | HTTP 401 | 合/否 |
| 2 | dept-a principal | 結果の `metadata.group` / `_source.group` が dept-a のみ | 合/否 |
| 3 | eval token | dept-a と dept-b の両方を取得可能 | 合/否 |
| 4 | 案3 DLS 直接検索 | dept-b 固有語の `hits.total.value` が 0 | 合/否 |

1件でも所属外文書が返れば不合格とする。

## 5. 不合格時の切り分け

1. 転送 JWT の `email` と `groups.json` のキーを照合する
2. Qdrant payload の `metadata.group`、OpenSearch document の `group` を確認する
3. rag-api の明示 filter と、案3の group role/DLS 定義を個別に確認する
