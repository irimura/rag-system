# セッションコンテキスト(コーディングエージェント向け引き継ぎ)

最終更新: 2026-08-03(§21 案1b RAG バッチ識別ログを追記)/ 対象ブランチ: main(リモートなし・ローカルのみ)

このリポジトリは **vLLM + LangChain による日本語 RAG システムの設計・構築・評価ドキュメント一式**である。コードよりドキュメントが主体で、`03-deployment/` のアプリコードはサンプル実装(構文検証済み・実ビルド/実行は未実施)。本ファイルは過去セッションの決定事項・規約・注意点の引き継ぎであり、**ここに書かれた決定を無断で覆さないこと**(変更するときはユーザーに確認する)。

## 1. プロジェクトの前提(ユーザー要件・確定事項)

- vLLM は Hugging Face 形式モデルで稼働させる。**vLLM 同梱の OpenAI 互換サーバ(`vllm serve` / `vllm/vllm-openai` イメージ)を使い、自前 API ラッパーは書かない**
- **無償利用可・ソース公開**のソフトウェアで構成する。クラウドのマネージドサービスは使わない(EC2 を素の VM として使うのは可)
- 日本語の取り扱いが精度要件に含まれる(正規化・形態素解析 BM25・日本語特化モデル等は `06-tuning/README.md` に集約)
- インフラは AWS EC2(東京 ap-northeast-1 想定)

### ノード命名(重要 — ユーザーが 2 度取り違えた経緯あり)

| ノード | 役割 | ホスト名 | Instance Type | AMI |
|---|---|---|---|---|
| **Node A** | GPU / vLLM(GPTQ 4bit・最大32k) | llm-001 | g6e.xlarge(最小)〜 g6e.2xlarge(推奨) | Deep Learning Base OSS Nvidia Driver GPU AMI (**Ubuntu 24.04**) |
| **Node A-2** | GPU / vLLM(GPTQ 8bit・最大16k) | llm-002 | g6e.xlarge(最小)〜 g6e.2xlarge(推奨) | 同上 |
| **Node A-3** | GPU / vLLM(16bit非量子化・最大32k) | llm-003 | p5.4xlarge(単一H100 80GB推奨) / g6e.12xlarge(TP=2)等 | 同上 |
| **Node B** | アプリ+データ(WebUI/RAG API/ベクトル DB/TEI) | app-001/002/003(案1/2/3) | t3.large / m7i.xlarge / r7i.xlarge(案別最小) | Ubuntu Server 24.04 LTS(素の Canonical AMI) |

- GPU 確定要件: **Ampere 世代以降・Node A/A-2はVRAM 40GB+、Node A-3は80GB+・CUDA 12.8 対応、NVIDIA Driver + NVIDIA Container Toolkit**
- **OS は Ubuntu 24.04 で確定**(利用する vLLM Docker イメージが 24.04 ベースのため。22.04 に戻さない)

## 2. リポジトリ構成と各ファイルの役割

**2026-07-17 に工程別のトップレベル構成へ再構成した(§17)。** ルート README.md の工程表が正のインデックス。各工程ディレクトリの README.md がその工程の主文書。概略:

- `README.md` — 工程インデックス(1 段落サマリ + 工程表のみのスリム構成)
- `01-design/` — 設計。`README.md`(全体設計・案1〜3比較・ライセンス一覧)、`plan{1,1b,2,3}-*.md`(実装案、案2 推奨。図は **Mermaid**)、`auth-oidc.md`、`node-specs.md`(EC2 スペック選定・料金。**東京・1USD=160JPY・常時730h/日中帯160h** が基準)
- `02-provisioning/` — 構築。`aws-provisioning.md`(AWS 構築 Bash 手順: VPC/SG/EICE/NAT/EC2/AMI 化/自動停止)、`node-a-pre-install.md`(Node A 単体の構築・確認手順。DLAMI 前提、手動導入は任意節)、`node-a/`(vLLM compose + systemd unit + .env.example)
- `03-deployment/` — デプロイ。`README.md`(Node B デプロイ手順、案1〜3)、`plan{1,1b,2,3}/`(compose/Dockerfile/アプリコード。rag-api は OpenAI 互換で公開し Open WebUI から 1 モデルに見せる設計。plan3/rag-api/tests/ にユニットテスト)、`keycloak/`
- `04-corpus/` — コーパス取り込み。`README.md`(取り込み手順)、`corpus-datasets.md`(投入用公開コーパス集)、`prerequisites.md` / `download.md` / `ingest-plan*.md`、`scripts/`(取得・前処理スクリプト)
- `05-evaluation/` — 精度評価。`README.md`(実行フロー)、`evaluation-spec.md`(2 段階評価: L1 HitRate/MRR/nDCG、L2 Ragas。TC01〜TC10)、`eval-datasets.md`(評価用 QA データセット集)、`golden_dataset.sample.jsonl`、`level1/` / `level2/`(実行スクリプト)、`cases/`(TC ケース手順書)
- `06-tuning/` — チューニング。`README.md`(Loader/Transformer/Embedding/VectorStore/Retriever/Rerank + 日本語固有ポイント)

## 3. AWS 設計の確定事項(02-provisioning/aws-provisioning.md)

- **単一プライベートサブネット** 192.168.0.0/26(VPC 192.168.0.0/24)に全ノード収容。固定プライベート IP(llm=.10/.11/.12, app=.21/.22/.23)
- **Route 53 PHZ は不採用**(固定 IP のメリット優先、とユーザーが明示判断)
- **NAT Gateway と IGW は「必要時のみ」**: セットアップ時に一時サブネット 192.168.0.64/28 ごと作成し、AMI 化後に **IGW も含めて**削除。定常運用はインターネット経路ゼロの隔離
- **シェルアクセスは EICE**(SSM ではない): 隔離状態でも接続可・無料・インスタンス IAM 不要が採用理由。EICE のトンネルは **22/3389 限定**のため、WebUI へは SSH の LocalForward(`~/.ssh/config` に `Host ragsys-*` 共通設定 + `ragsys-llm-001` / `ragsys-app-00N` を登録、`ssh -N ragsys-app-002` で接続)
- **毎日 18:00 JST に EC2 自動停止**(EventBridge Scheduler → `ec2:stopInstances` 直接呼び出し、Lambda 不要。§1.5)
- vLLM は `--api-key` 必須運用。Node B の `.env` の `VLLM_MODEL`/`VLLM_API_KEY` は Node A の `SERVED_MODEL_NAME`/`--api-key` と一致させる

## 4. 執筆・コマンド規約(ユーザー指定 — 必ず順守)

1. `mv` / `cp` / `rm` / `mkdir` / `rmdir` / `install` には **`-v`** を付ける(再帰 rm で大量出力が予想される場合は除く)。`chmod` / `chgrp` / `chown` には **`-c`** を付ける
2. `vi` ではなく **`vim`**
3. リダイレクトは **`cat` + ヒアドキュメント**(単行の `echo | tee` も変換対象)
4. 実行用の shell コマンド中の未確定値はプレースホルダ `<foo>` ではなく **`${foo}` 変数**にし、ドキュメント冒頭に「実行前に置き換える」旨を注記。systemd 等の非 shell 設定テンプレートの `<your-...>` と、本文中で構文を説明する `<type>` は適用外
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

- `03-deployment/` のアプリコード(rag-api 等)は**未ビルド・未実行**(py_compile と設計レビューのみ)。初回起動時の不具合修正はあり得る
- `05-evaluation/golden_dataset.sample.jsonl` の正解値は**取り込む法令の版で要確認**(サンプルの位置づけ)
- Ragas は API 変更が多いため、`05-evaluation/level2/requirements.txt` で 0.2 系へ固定済み。`pip freeze` は解決されたパッチ版の実験記録に使い、0.4 系へ上げる場合はコードも同時移行する
- `05-evaluation/` の実行スクリプトは案2(Qdrant+TEI)前提。案1/案3 への読み替えは各 procedure.md 末尾に記載
- plan1 の文書には venv+systemd 手順が「コンテナを使わない場合の代替」として残っている(Docker 版が正)
- TC09(会話文脈)は現行 rag-api 実装が弱い設計と明記済み(history-aware 書き換えは将来改善)

## 8. Codex 一次レビューの検証結果(2026-07-13 / Claude Code)

Codex の一次レビュー R-01〜R-10 を独立検証した。**判定・根拠・行番号・公式 URL の詳細はコミット `b511fe8` 時点の `agent/review.md` / `agent/regression-review.md` (git 履歴)を参照**し、本節は要点のみ。検証時 HEAD = `de161d4`。

- **誤りと判定した指摘はない**(R-10-⑥のみ「規約の適用除外が未明文化」への再解釈)
- **確認済みの重要指摘(修正対象)**:
  - R-01: L1 評価の過大評価(is_hit の doc_id 一致 / IDCG が取得ヒット数基準 — 数値再現済み: evidence 2 件中 1 件取得でも nDCG=1.000)
  - R-02: 評価コードが rag-api の検索経路(MMR・rerank 閾値・NO_ANSWER 分岐)を再現していない
  - R-03: 再取り込みで重複チャンク(Qdrant・Chroma とも既定 ID=uuid4 を LangChain 公式ソースで確認。splitter は元 Document.id を引き継がない。**plan1 には FORCE_RECREATE 自体がない**)
  - R-04: LangChain v1 で `langchain.retrievers` → `langchain-classic` 移動、Ragas 現行 v0.4 で `evaluate()` 廃止(いずれも公式移行ガイドで確認)。未固定 requirements のままでは plan1 / level2 スクリプトが新規インストールで動かない
  - R-07: 案3 の再検索が同一書き換えの反復になる(question のみ・temperature=0)
  - R-08-①②③: node-a-pre-install に固定 IP 指定なし / §5.3 の deregister→snap_id 順序矛盾 / EICE 削除の待機なし
  - R-10-①〜⑤: 文書と実装のずれ(22.04 併記、README 比較表の venv+systemd、plan3 図の PG ジョブ状態、plan2 healthcheck、plan1 説明コードの e5 プレフィックス欠落)
- **ユーザー決定(2026-07-13)— 4 点すべて確定済み**:
  - R-05 = **(a)**: 要件文言を「無償利用可・ソース公開」へ調整し、Open WebUI は維持(README ライセンス表の記述は現状のまま正確)
  - R-06 = **(b)**: 案3 に OpenSearch Security Plugin **有効化手順を正式追加**(compose・証明書・初期管理者パスワード・rag-api / ingest のクライアント認証対応・docs 更新を含む。修正フェーズの主要作業項目)
  - R-08-④ = **ホスト鍵検証の無効化を受容**(`StrictHostKeyChecking no` は現状維持。「EICE/IAM で保護済み」の過大表現の適正化のみ実施)
  - R-09 = **検証フェーズはマイナーバージョンまで固定**(コンテナタグ・Python 依存とも)。digest 固定等の最終方針は運用設計フェーズで確定
- **未確認(持ち越し)**: OpenSearch `knn_vector` の lucene+cosinesimil 対応の公式記載、OpenSearch「Security 無効化は非推奨」のそのものの明文(警告 2 件は確認済み)
- **修正フェーズ完了(2026-07-14 / 基準 `dd6ab3d`、変更は未コミット)**:
  - R-01/R-02: quote のみの根拠判定、Evidence Recall、正しい IDCG・重複排除を実装し、案2 rag-api の本番検索関数と OpenAI 互換 API を評価から直接使用
  - R-03/R-04/R-09: 3 案の取り込みを全量再構築へ統一し、コンテナと Python 依存をマイナー系列まで固定(digest は未固定)
  - R-06/R-07: OpenSearch Security Plugin を有効化し、検証用 CA / TLS、初期管理者、検索専用 / 更新専用ユーザー、初期化サービスを追加。再検索は試行回数と検索済みクエリを渡す
  - R-05/R-08/R-10: 決定済み文言、AWS 手順 4 件、Ubuntu 24.04・案1デプロイ・各説明図 / コードの不整合を修正
  - 追加整合修正: 案3の `rag-api` / `ingest` へ初期管理者パスワードを渡さないよう compose の環境変数を限定し、評価仕様に案2 / 案3の `RERANK_TOP_N` 既定値差を明記
- **修正後検証**: Python 全 16 ファイルの AST、JSON 2 ファイル、JSONL 10 行、Markdown 22 ファイル / ローカルリンク 95 件 / コードフェンス、単体テスト 6 件、requirements 制約、浮動コンテナタグ、`git diff --check` は合格
- **未検証**: Docker CLI 不在のため compose config / build / 起動、OpenSearch の実接続・認可、AWS 資格情報を使う実操作は未実施。bash / shellcheck も利用不可のため AWS コマンドブロックは静的確認のみ
- **回帰レビュー N-01〜N-04 対応(2026-07-14、未コミット)**:
  - N-01: Docker CLI は不在。公式 `opensearch-build` 2.19.6 の Dockerfile / entrypoint と Security Plugin 2.19.6.0 のソースから、demo 設定はイメージビルド時に無効で、`root-ca.pem` はコンテナ起動時に `config/` へ配置されることを確認。`rag-api` の build-stage COPY を削除し、OpenSearch を先に起動して CA をホストへ取り出し、`rag-api` / `security-init` / `ingest` へ読み取り専用 mount する手順へ変更。イメージ内ファイル一覧と実 build は未確認
  - N-02: 同版の埋め込みノード証明書を静的解析し、SAN の `node-0.example.com` と compose alias の一致を確認。追試で、`opensearch-py` 2.8.0 の `indices.exists()` は `HEAD /{index}`、OpenSearch 2.19.6 の同ルートは `GetIndexAction.NAME = indices:admin/get` を実行すると判明したため、`rag_reader` の明示権限を誤っていた `indices:admin/exists` から `indices:admin/get` へ修正。`rag_ingest` の `indices_all`、demo 設定の admin REST 有効ロールは静的確認済み。security-init 終了コード 0、TLS 実接続、Security REST API、health / 実検索、更新可否の実測は Docker 不在のため未確認
  - N-03: 案2の評価 endpoint は認可を追加せず、同一 Docker network からも到達可能という実態を保ったまま、docstring を「認可なし・ホスト公開だけ 127.0.0.1 限定」へ修正
  - N-04: `.env.example` / `docker-compose.yml` / `rag-api/Dockerfile` の末尾へ LF を 1 byte 追加。3 ファイルとも既存の LF 改行形式を維持
  - 回帰修正後検証: Python 16 ファイル、単体テスト 6 件、JSON 2 ファイル、JSONL 10 行、Markdown 23 ファイル / ローカルリンク 151 件 / コードフェンス、requirements 5 ファイル 39 依存、コンテナ参照 14 件、静的 Security / CA 境界、`git diff --check` は合格

## 9. これまでの主な意思決定の流れ(時系列要約)

初期設計(案1〜3 + 構成要素解説)→ 2 ノード分離(GPU/アプリ)→ BM25 を明示的な選択肢に → 日本語固有チューニング加筆 → 評価仕様 + 公開テストデータ → Node B 構築ファイル一式 → Node A は vLLM 同梱サーバで確定 → CLI 規約適用 → EC2 スペック/AMI/料金 → GPU 要件確定(Ampere+/40GB/CUDA12.8)→ node-a-vllm.md は削除(内容は deploy/node-a/ と node-specs.md に集約)→ AWS 構築手順(単一サブネット・一時 NAT+IGW・EICE・自動停止)→ node-a-pre-install.md を設計と整合(Ubuntu 24.04 確定)

詳細は `git log`(コミットメッセージが決定理由を含む)を参照。

## 10. OIDC 認証・グループ認可の決定事項(2026-07-15)

詳細設計は [01-design/auth-oidc.md](../01-design/auth-oidc.md)を正とする。デプロイコード変更は次フェーズ。

- 本番 IdP は **外部ネットワーク(The Internet / 別 VPC)** 上に置く。フロントチャネルは利用端末から直接接続し、Node B から discovery/token endpoint へのバックチャネル経路を別途整備する
- バックチャネルは The Internet 上の IdP 向け **NAT Gateway 常設**と、別 VPC 上の IdP 向け **VPC ピアリング**を両論併記する。具体手順は `02-provisioning/aws-provisioning.md` §2.3 を正とする
- 検証用 IdP は **Keycloak**。外部 IdP の開通・経路整備前に OIDC フロー全体をネットワーク変更なしで先行検証する専用手段として維持し、本番運用では profile `idp` を起動しない
- Open WebUI はローカル login form と OIDC を併存させ、検証中は手動グループ、本番は IdP group claim 同期へ移行する
- 案2/3 の rag-api は認証方式非依存の principal とグループ解決を実装し、Vector DB 検索へ `group` filter を強制する。これは **N-03(rag-api 無認可)** の恒久対応方針
- Qdrant は **単一 collection + payload filter**、OpenSearch は **単一 index + `group` DLS**。グループ別 collection/index はライフサイクル分離要件がある場合のみ
- 案3は rag-api と OpenSearch Security の二層認可。internal user/backend role から OIDC auth domain(`roles_key: groups`)へ段階移行する
- ingest は全チャンクへ `group` を付与して全再取り込みし、eval には専用グループ/利用者/token を用意する
- 実装フェーズでは Open WebUI を v0.9.6 へ更新する。署名付き `X-OpenWebUI-User-Jwt` が利用できる最小版であり、rag-api は JWT 欠落・不正を 401 として平文ヘッダーを信頼しない
- ローカル所属は案2/3 の `auth/groups.json`、文書所属は `documents/<group>/...` の第1階層を正とする。直下ファイルと未知/空所属は fail closed
- 案3の暫定方式はグループ別 OpenSearch internal user + DLS。Token Exchange は将来パス
- 評価経路は `EVAL_TOKEN` を `secrets.compare_digest` で検証し、全グループ principal として TC11 の越境試験に使用する

## 11. 案1b・案2の NGINX/TLS 統一(2026-07-16)

- 案1b・案2も案3と同じ `nginx:1.30.4` を Open WebUI 前段へ置き、外部公開は 80/443(TLS 終端)に統一した。案1(Chainlit)は変更しない
- Open WebUI のホスト 3000 は `127.0.0.1:3000:8080` のデバッグ用途だけとし、NGINX はコンテナ内 `open-webui:8080` へプロキシする
- `03-deployment/plan1b/nginx/conf.d/rag.conf` と `03-deployment/plan2/nginx/conf.d/rag.conf` は案3と同一。証明書生成物は Git 管理せず `.gitkeep` だけ保持する
- NGINX の常駐オーバーヘッドは軽微なため、案1b・案2の推奨 Instance Type は据え置く
- 検証環境に Docker CLI がないため、`docker compose config`、自己署名証明書での起動、HTTP 301 / HTTPS 200、3000 の loopback bind、ブラウザでの SSE/WebSocket・アップロードは未検証。NGINX 設定3案の SHA-256 一致と静的検証のみ実施した

## 12. NGINX 脆弱性対応: 1.30.3 → 1.30.4(2026-07-16)

- nginx の脆弱性 3 件(CVE-2026-42533: map ディレクティブのヒープバッファオーバーフロー Critical 9.2 / CVE-2026-60005: slice module High 8.8 / CVE-2026-56434: SSI module High 8.3)への対応として、3案の nginx イメージを `nginx:1.30.4` へ更新した
- `rag.conf` は WebSocket 対応で `map` ディレクティブを使用しており CVE-2026-42533 の影響を受けるため更新必須だった(slice/SSI は未使用)
- R-09 決定「検証フェーズはマイナー系列固定」に従い、mainline 1.31 系へは乗り換えず stable 系列内のパッチ更新とした。`nginx:1.30.4` タグは Docker Hub に 2026-07-16 公開済みであることを確認した
- 稼働環境では `docker compose pull nginx && docker compose up -d nginx` で反映し、`nginx -v` と https 経路の再確認を行うこと

## 13. 段階別コーパス取り込み手順(2026-07-16)

- `04-corpus/scripts/`(当時 `scripts/corpus/`)を新設し、共通 `corpus.env`、e-Gov/情報通信白書/IPA/livedoor/Wikipedia の取得、法令/Wikipedia の前処理、段階別配置、固定依存、スクリプト索引を追加した
- `04-corpus/`(当時 `docs/corpus/`)を新設し、全体マトリクス、事前準備、コーパス別取得・検収、案1/1b/2/3別の投入・検収・トラブルシュートを追加した
- 文書配置グループは **`laws` / `whitepaper` / `ipa` / `livedoor` / `wikipedia`** に固定する。案2/3では `documents/<group>/...` の第1階層を認可メタデータとし、直下ファイルは fail closed。案1も移行互換のため同じ配置を使う
- 案1/2/3は段階が進むたびに `documents/` へ累積配置し、既存コレクション/インデックスを削除して全量再取り込みする。差分だけでは実行しない
- 案1bは `documents/` / `ingest.py` を持たないため、Open WebUIの private Knowledgeへ UI/API で追加する。数十万チャンク以上の段階3(負荷・規模試験)は対象外とし、案2/3へ移行する
- livedoorは CC BY-ND 2.1 JPの改変禁止・社内評価限定を維持し、本文の書き換え/要約保存/成果物再配布を行わない。Wikipediaは CC BY-SA 4.0、政府/IPA資料は出典を保持する
- 静的検証: corpus用 bash 7ファイルの `bash -n`、Python 2ファイルの `py_compile`、`docs/corpus/` 7ファイルのローカルリンク/アンカー/コードフェンス/CLI規約、`git diff --check` は合格
- **未確認**: Node Bから各公式URLへの疎通とダウンロード、実コーパスを用いた前処理スクリプト実行、WikiExtractor/PDF抽出品質、Docker ingest、件数照合、Open WebUI UI/APIアップロード、ACL/DLS、所要時間・容量の実測

## 14. コーパス取り込みレビュー修正(2026-07-16)

- 段階3の標準配置を3案とも `copy` に統一した。`symlink` は `${CORPUS_DIR}` を ingestコンテナへ同じ絶対パスで read-only追加マウントした場合だけ使用でき、スクリプト実行時にも注意を表示する
- `prepare_stage.sh` は `SOURCE.md` / `LICENSE.txt` / `CHANGES.txt` / `README.txt` を配置対象から除外し、出典・ライセンス確認用ファイルが検索チャンクへ混入しないようにした
- livedoorアーカイブの保存名は `LIVEDOOR_URL` の basenameから導出し、URL差し替え時にも対応する
- ルート `.gitignore` に `.venv-corpus/` を追加した
- 検証: corpus用 bash 7ファイルの `bash -n`、一時コーパスで copy/symlink各5ファイルの配置と付随4ファイル名の除外、livedoor保存名導出、Markdown 9ファイル/ローカルリンク44件、`git diff --check` は合格
- **未確認**: Node BのDockerコンテナで `${CORPUS_DIR}` 追加マウント後のsymlink追従、実コーパスによる全量ingest

## 15. agent/ ディレクトリの運用整理(2026-07-17)

- `agent/` 配下で恒久的に維持するファイルは `session.md` のみとし、引き継ぐべき決定・要点・未確認事項を本ファイルへ集約する
- 役割を終えた `review.md`、`regression-review.md`、`claude-review-prompt.md`、`codex-corpus-prompt.md` を削除した
- レビュー記録・エージェント間の依頼プロンプト・作業メモ等を同じ作業単位内で削除し、次のエージェントへ残留させないルールを `AGENTS.md` に新設した
- 削除したレビュー記録の詳細はコミット `b511fe8` 時点の `agent/review.md` / `agent/regression-review.md` を含む git 履歴を参照する

## 16. Markdown H1・Node A 事前構築文書の命名(2026-07-17)

- Markdown の H1 は工程番号やディレクトリパスを含めず、「対象 + 文書種別」の形で文書内容を単体で判別できる表現にする
- Node A の文書名は `02-provisioning/node-a-pre-install.md`、H1 は「Node A 事前構築手順書」とする。「事前」は、この後に機密の vLLM 配置作業を別途実施する位置づけを示すため維持する

## 17. 工程別リポジトリ再構成(2026-07-17)

旧 `docs/ deploy/ eval/ scripts/ test/` を廃止し、工程別のトップレベル 6 ディレクトリ(ケバブケース + 番号接頭辞)へ再構成した(マージコミット `8f50495`)。現在の構成は §2 を参照。主な対応:

- `docs/` の設計文書 → `01-design/`、AWS/Node A 手順 → `02-provisioning/`(`deploy/node-a/` も 02 へ)
- `deploy/plan*` + `deployment-guide.md` → `03-deployment/`(deployment-guide.md は `03-deployment/README.md` へ昇格)
- `docs/corpus/` + `scripts/corpus/` → `04-corpus/`(scripts は `04-corpus/scripts/`)
- `docs/evaluation-spec.md` + `test/` + `eval/` → `05-evaluation/`。ただし `test/plan3/test_query_rewrite.py` はコード隣接の `03-deployment/plan3/rag-api/tests/` へ
- `docs/rag-components.md` → `06-tuning/README.md` へ昇格
- `docs/test-data.md` は 2 分割: 投入用コーパス → `04-corpus/corpus-datasets.md`、評価用 QA/ベンチマーク/合成データ → `05-evaluation/eval-datasets.md`
- 慣行: **各工程ディレクトリの README.md = その工程の主文書**(02 のみ 2 手順の使い分けを示す入口文書)。ルート README は工程インデックスに限定
- 本ファイルの §2・§3・§7・§10・§11・§13 のパス表記は再構成後のものへ更新済み。§8・§9 は履歴記述のため当時のパスのまま(実体は git 履歴で追跡可能)

## 18. §2.2 の NAT 関連 ID 再取得(2026-07-17)

- 問題: `02-provisioning/aws-provisioning.md` §2.2 が使う `${nat_id}` `${eip_alloc}` `${nat_assoc_id}` `${nat_rtb_id}` `${nat_subnet_id}` を §5.1 が取得しておらず、「§5.1 のタグ検索で再取得」という注記が実態と不一致だった。シェルを閉じると、稼働時間課金の NAT Gateway を削除できない状態になっていた
- 対応: **§2.2 自身に ID 再取得ブロックを追加**して単独実行可能にした(§2 は §5 と実行タイミングが異なる独立したライフサイクルのため、§5.1 に NAT 変数を足す方式は採らない)。コミット `4660280`
- **AWS CLI の注意点(再発防止)**: `describe-nat-gateways` はオプション名が **`--filter`(単数形)** で、他の `describe-*`(`--filters` 複数形)と異なる。また削除済み NAT が一定期間応答に残るため、**`Name=state,Values=available` での絞り込みが必須**
- 検証済み: 削除ブロックが使う 8 変数すべてが再取得ブロックで充足、`nat_assoc_id` → `nat_rtb_id` の順序依存も正しい、再取得+削除を連結した `bash -n`、§2.3 経路A(NAT 常設)・§5.2 手順3 との整合、`git diff --check`
- **未実施**: 実 AWS リソースでの再取得・削除の動作確認(コマンドは静的検証のみ)

## 19. Locust 性能測定ノードと手順(2026-07-29)

- 性能測定専用ノード `perf-001` を追加した。固定プライベート IP は `192.168.0.20`、Instance Type は `t3.medium`、ルート EBS は gp3 30GB、AMI は Node B と同じ Ubuntu 24.04
- perf-001 は既存ワークロードサブネットと単一 SG に収容し、EICE 経由で管理する。Locust Web UI は `ragsys-perf-001` の SSH LocalForward 8089 で管理者端末へ転送する
- Locust は Open WebUI の nginx 443 経由で測定し、ユーザー体感に近い応答時間を対象とする。案1(Chainlit)は対象外で、案1b / 案2 / 案3を測定する。同一 SG 内通信は許可済みのため SG 変更は不要
- `07-performance/` に perf-001 セットアップ、Headless / Web UI の測定・判定・記録・クリーンアップ手順、`POST /api/chat/completions` 用 `locustfile.py` を集約した
- 性能指標を TTFT / TPOT(ITL) / Output token throughput / Request throughput の 4 指標へ拡張し、Locust は Open WebUI の SSE を逐次読みしてコンテンツチャンク数をトークン数の近似として計測する
- 案3 rag-api は LangGraph を検索・リトライ・ルート判定までに縮め、生成をエンドポイントへ移して `llm.astream()` による真のトークンストリーミングへ改修した

## 20. GPU 推論ノード増設(2026-07-30)

- 既存 Node A は GPTQ 4bit・最大32k・VRAM 40GB以上。Node A-2(GPTQ 8bit・最大16k・40GB以上)と Node A-3(16bit非量子化・最大32k・80GB以上)を追加し、GPU 3ノード + Node B構成へ変更した
- Node A/A-2は単一L40Sのg6e.2xlarge推奨(g6e.xlarge最小)。Node A-3は単一GPU 80GBを原則としp5.4xlargeを推奨。代替としてg6e.12xlarge搭載4×L40Sのうち2GPUを`--tensor-parallel-size 2`で使う案を許容する
- vLLMは全ノード`--gpu-memory-utilization 0.90`。最大長はA-2=16384、A-3=32768。Node A既存設定の8192は32k対応モデルの初期運用値として維持した
- `02-provisioning/node-a/docker-compose.yml`と`vllm.service`を共通資材とし、`node-a-2/`・`node-a-3/`にノード別`.env.example`と利用READMEを置く
- 全ノードは単一 SG の自己参照ルールで相互通信し、vLLM は全 GPU ノードで`--api-key`必須(多層防御)、Ubuntu 24.04 DLAMI、CUDA 12.8、夜間停止の既存方針を維持する

## 21. 案1b Open WebUI RAG バッチ識別ログ(2026-08-03)

- Open WebUI v0.9.6 の内蔵 Sentence Transformers が出す複数の `Batches` tqdm 表示を、embedding / rerank を判別できる開始・終了ログへ置き換えるカスタムイメージを `03-deployment/plan1b/open-webui/` に追加した
- 各呼び出しへ `emb-...` / `rerank-...` の一意 ID を付け、入力件数、設定バッチサイズ、予定バッチ数、成否、所要時間(ms)を INFO で記録する。プロンプトやチャンク本文は記録しない
- `show_progress_bar=False` は内部 embedding と内部 CrossEncoder rerank の両方に指定する。RAG の検索結果・並列処理・モデル設定は変更しない
- 公式イメージ内の対象コードが想定と異なる場合はビルドを失敗させ、別バージョンへ誤適用しない。ベースイメージは既存決定どおり v0.9.6 固定
- 公式 v0.9.6 ソースへのパッチ適用、Python 構文、`docker compose config` は検証済み。Docker daemon が起動していないため、実コンテナ build / 起動 / 実質問ログは未確認
