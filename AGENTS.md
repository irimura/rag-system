# AGENTS.md — コーディングエージェント向けガイド

このリポジトリで作業を始める前に、**必ず [agent/session.md](agent/session.md) を読むこと。**
過去セッションの決定事項・設計の根拠・執筆規約・既知の罠がすべてそこに集約されている。ここに書かれた決定(ノード命名、Ubuntu 24.04、EICE 採用、一時 NAT+IGW、固定プライベート IP 等)を、ユーザー確認なしに覆さないこと。

## リポジトリ概要(1 分版)

vLLM + LangChain による日本語 RAG システムの設計・構築・評価ドキュメント一式。ドキュメント主体で、`deploy/` のコードはサンプル実装(未ビルド・未実行)。全体のインデックスは [README.md](README.md) の「ドキュメント構成」表。

## 最低限の規約(詳細と背景は agent/session.md §4〜6)

- ドキュメントは日本語、図は Mermaid、コミットメッセージは英語(1 コミット = 1 論理変更、`Co-Authored-By: Claude <モデル名> <noreply@anthropic.com>` を付す)
- 手順書のコマンド: `mv/cp/rm/mkdir/rmdir/install` に `-v`、`vi`→`vim`、`chmod/chgrp/chown` に `-c`、'リダイレクトは `cat` + ヒアドキュメント、未確定値は `${foo}` 変数、bash 変数は `${var}` でブレース統一、コマンドは 1 行に
- ノード命名: **Node A = GPU(vLLM)/ Node B = アプリ+データ**。取り違え注意
- 作業前に `git status` を確認(ユーザーが直接編集していることがある)
- 外部 URL・ライセンス・料金を書くときは Web で実在確認してから

## 主要ドキュメントへのショートカット

| 知りたいこと | 参照先 |
|---|---|
| 全体設計・実装案の比較 | [README.md](README.md) |
| AWS 構築(VPC/EICE/NAT/自動停止) | [docs/aws-provisioning.md](docs/aws-provisioning.md) |
| EC2 スペック・AMI・料金 | [docs/node-specs.md](docs/node-specs.md) |
| Node A / Node B の構築手順 | [docs/node-a-pre-install.md](docs/node-a-pre-install.md) / [docs/deployment-guide.md](docs/deployment-guide.md) |
| 精度評価のやり方 | [docs/evaluation-spec.md](docs/evaluation-spec.md) + [test/](test/) |
| 過去の決定理由 | [agent/session.md](agent/session.md) + `git log`(コミットメッセージに理由を記載) |
