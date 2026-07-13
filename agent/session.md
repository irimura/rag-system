# セッションコンテキスト(コーディングエージェント向け引き継ぎ)

最終更新: 2026-07-13 / 対象ブランチ: main(リモートなし・ローカルのみ)

このリポジトリは **vLLM + LangChain による日本語 RAG システムの設計・構築・評価ドキュメント一式**である。コードよりドキュメントが主体で、`deploy/` のアプリコードはサンプル実装(構文検証済み・実ビルド/実行は未実施)。本ファイルは過去セッションの決定事項・規約・注意点の引き継ぎであり、**ここに書かれた決定を無断で覆さないこと**(変更するときはユーザーに確認する)。

## 1. プロジェクトの前提(ユーザー要件・確定事項)

- vLLM は Hugging Face 形式モデルで稼働させる。**vLLM 同梱の OpenAI 互換サーバ(`vllm serve` / `vllm/vllm-openai` イメージ)を使い、自前 API ラッパーは書かない**
- **すべて無償 OSS**。クラウドのマネージドサービスは使わない(EC2 を素の VM として使うのは可)
- 日本語の取り扱いが精度要件に含まれる(正規化・形態素解析 BM25・日本語特化モデル等は docs/rag-components.md に集約)
- インフラは AWS EC2(東京 ap-northeast-1 想定)

### ノード命名(重要 — ユーザーが 2 度取り違えた経緯あり)

| ノード | 役割 | ホスト名 | Instance Type | AMI |
|---|---|---|---|---|
| **Node A** | GPU / vLLM 推論専用 | llm-001 | g6e.xlarge(最小)〜 g6e.2xlarge(推奨) | Deep Learning Base OSS Nvidia Driver GPU AMI (**Ubuntu 24.04**) |
| **Node B** | アプリ+データ(WebUI/RAG API/検索DB/TEI) | app-001/002/003(案1/2/3) | t3.large / m7i.xlarge / r7i.xlarge(案別最小) | Ubuntu Server 24.04 LTS(素の Canonical AMI) |

- GPU 確定要件: **Ampere 世代以降・VRAM 40GB+・CUDA 12.8 対応、NVIDIA Driver + NVIDIA Container Toolkit**
- **OS は Ubuntu 24.04 で確定**(利用する vLLM Docker イメージが 24.04 ベースのため。22.04 に戻さない)

## 2. リポジトリ構成と各ファイルの役割

README.md の「ドキュメント構成」表が正のインデックス。概略:

- `README.md` — 全体設計・案1〜3比較・ライセンス一覧
- `docs/plan{1,2,3}-*.md` — 実装案(案2 推奨)。図は **Mermaid**
- `docs/rag-components.md` — Loader/Transformer/Embedding/VectorStore/Retriever/Rerank + 日本語固有ポイント
- `docs/evaluation-spec.md` + `test/` + `eval/` — 2 段階評価(L1: HitRate/MRR/nDCG、L2: Ragas)・TC01〜TC10・実行スクリプト
- `docs/test-data.md` — 公開コーパス/QA データセット(URL・ライセンスは Web で実在確認済み)
- `docs/node-specs.md` — EC2 スペック選定・料金(**東京・1USD=160JPY・常時730h/日中帯160h** が基準)
- `docs/aws-provisioning.md` — AWS 構築 Bash 手順(VPC/SG/EICE/NAT/EC2/AMI 化/自動停止)
- `docs/node-a-pre-install.md` — Node A 単体の構築・確認手順(DLAMI 前提、手動導入は任意節)
- `docs/deployment-guide.md` — Node B 構築手順(案1〜3)
- `deploy/node-a/` — vLLM compose + systemd unit + .env.example
- `deploy/plan{1,2,3}/` — Node B の compose/Dockerfile/アプリコード(rag-api は OpenAI 互換で公開し Open WebUI から 1 モデルに見せる設計)

## 3. AWS 設計の確定事項(docs/aws-provisioning.md)

- **単一プライベートサブネット** 192.168.0.0/26(VPC 192.168.0.0/24)に全ノード収容。固定プライベート IP(llm=.10, app=.21/.22/.23)
- **Route 53 PHZ は不採用**(固定 IP のメリット優先、とユーザーが明示判断)
- **NAT Gateway と IGW は「必要時のみ」**: セットアップ時に一時サブネット 192.168.0.64/28 ごと作成し、AMI 化後に **IGW も含めて**削除。定常運用はインターネット経路ゼロの隔離
- **シェルアクセスは EICE**(SSM ではない): 隔離状態でも接続可・無料・インスタンス IAM 不要が採用理由。EICE のトンネルは **22/3389 限定**のため、WebUI へは SSH の LocalForward(`~/.ssh/config` に `Host ragsys-*` 共通設定 + `ragsys-llm-001` / `ragsys-app-00N` を登録、`ssh -N ragsys-app-002` で接続)
- **毎日 18:00 JST に EC2 自動停止**(EventBridge Scheduler → `ec2:stopInstances` 直接呼び出し、Lambda 不要。§1.5)
- vLLM は `--api-key` 必須運用。Node B の `.env` の `VLLM_MODEL`/`VLLM_API_KEY` は Node A の `SERVED_MODEL_NAME`/`--api-key` と一致させる

## 4. 執筆・コマンド規約(ユーザー指定 — 必ず順守)

1. `mv` / `cp` / `rm` / `mkdir` / `rmdir` / `install` には **`-v`** を付ける(再帰 rm で大量出力が予想される場合は除く)。`chmod` / `chgrp` / `chown` には **`-c`** を付ける
2. `vi` ではなく **`vim`**
3. リダイレクトは **`cat` + ヒアドキュメント**(単行の `echo | tee` も変換対象)
4. 未確定値はプレースホルダ `<foo>` ではなく **`${foo}` 変数**にし、ドキュメント冒頭に「実行前に置き換える」旨を注記
5. bash コードブロック内の変数は **`${var}` でブレース統一**(`$(...)` コマンド置換、nginx 設定の `$host` 等は対象外)
6. コマンドはコピペしやすいよう**なるべく 1 行に**(ユーザー自身が改行削減の編集をすることがある)
7. ドキュメントは日本語、図は Mermaid、料金は「東京・1USD=160JPY・730h/160h」基準

## 5. Git 運用規約

- コミットメッセージは**英語**、1 コミット = 1 論理変更。末尾に `Co-Authored-By: Claude <モデル名> <noreply@anthropic.com>`
- **ユーザーが直接ファイルを編集していることがある**。作業前に `git status` を確認し、ユーザーの未コミット変更は(依頼があれば)自分の変更より先に別コミットにする
- リモートなし。push 不要

## 6. 過去に踏んだ罠(再発防止)

- **Windows Python の text モード書き込みは LF→CRLF に変えてしまう**。一括変換スクリプトはバイナリ I/O(`open(path,"rb"/"wb")`)で書くこと(d18635d で全行 diff 事故→修正済み)
- **Windows Python の subprocess から git-bash の `bash -n` を呼ぶとパス不一致で空振りする**(全ブロック SYNTAX ERROR かつ stderr 空、は偽陽性)。検証は git-bash 内で `$HOME` 配下に書いて実行する
- ヒアドキュメント検証用の外側ラッパー(`<<'OUTER'`)の記法を**本文に混入させない**(ef0fefb で `cat <<__EOF__>> ... <<EOF` という壊れた行を修正した実績あり)
- EventBridge Scheduler の `update-schedule` は全定義必須(`--state` だけの部分更新は不可)。一時停止は削除→再作成で案内
- OpenSearch: `analysis-kuromoji` は標準イメージ非同梱(カスタム Dockerfile でインストール)、`vm.max_map_count=262144` 必須
- vLLM コンテナは `ipc: host` 必須。compose の `command:` はイメージ ENTRYPOINT(`python3 -m vllm.entrypoints.openai.api_server`)への引数
- multilingual-e5 系は `query:`/`passage:` プレフィックス必須(plan1 の `common.py` が自動付与。TEI 構成の既定は bge-m3 なので不要)
- 外部 URL・ライセンス・料金を資料に書くときは WebSearch/WebFetch で実在確認してから書く(このセッションの慣行)

## 7. 未完了・注意付きの項目

- `deploy/` のアプリコード(rag-api 等)は**未ビルド・未実行**(py_compile と設計レビューのみ)。初回起動時の不具合修正はあり得る
- `eval/golden_dataset.sample.jsonl` の正解値は**取り込む法令の版で要確認**(サンプルの位置づけ)
- Ragas は API 変更が多く、`test/level2/run_level2.py` は ragas 0.2 系想定のサンプル。実行時にバージョン固定(`pip freeze`)が前提
- `test/` のスクリプトは案2(Qdrant+TEI)前提。案1/案3 への読み替えは各 procedure.md 末尾に記載
- plan1 の文書には venv+systemd 手順が「コンテナを使わない場合の代替」として残っている(Docker 版が正)
- TC09(会話文脈)は現行 rag-api 実装が弱い設計と明記済み(history-aware 書き換えは将来改善)

## 8. これまでの主な意思決定の流れ(時系列要約)

初期設計(案1〜3 + 構成要素解説)→ 2 ノード分離(GPU/アプリ)→ BM25 を明示的な選択肢に → 日本語固有チューニング加筆 → 評価仕様 + 公開テストデータ → Node B 構築ファイル一式 → Node A は vLLM 同梱サーバで確定 → CLI 規約適用 → EC2 スペック/AMI/料金 → GPU 要件確定(Ampere+/40GB/CUDA12.8)→ node-a-vllm.md は削除(内容は deploy/node-a/ と node-specs.md に集約)→ AWS 構築手順(単一サブネット・一時 NAT+IGW・EICE・自動停止)→ node-a-pre-install.md を設計と整合(Ubuntu 24.04 確定)

詳細は `git log`(コミットメッセージが決定理由を含む)を参照。
