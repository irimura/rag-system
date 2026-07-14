# 回帰レビュー記録 — Codex 修正フェーズ(R-01〜R-10)の独立検証

## 0. 文書ステータス

| 項目 | 内容 |
|---|---|
| ステータス | **検証完了(未コミット作業ツリーに対する回帰レビュー)** |
| レビュー対象 | Codex による R-01〜R-10 修正(未ステージ・未コミット) |
| 基準コミット | `dd6ab3d`(HEAD も `dd6ab3d`。変更はすべて未コミットのため `git diff dd6ab3d..HEAD` は空) |
| レビュー方法 | `git status`/`git diff`/`git ls-files --others` による差分把握、未追跡ファイル全文確認、Python AST コンパイル、追加単体テスト実行(6 件)、JSON/JSONL 検証、Markdown コードフェンス/ローカルリンク検証、requirements ピン確認、浮動タグ grep、`git diff --check` |
| レビュアー | Claude Code(Opus 4.8)/ 2026-07-14 / Windows + git-bash・Python 3.12.10 |
| 未実施(実行環境なし) | Docker build/compose・OpenSearch Security REST API と TLS 実接続・AWS CLI 実行・依存パッケージの実 import・RAG 実データ評価。bash/shellcheck 不在のため AWS シェルブロックは静的確認のみ |
| 検証の前提 | `agent/session.md` §8「修正フェーズ完了」の記録は**正しいと仮定せず**、差分から独立に判定した |

**結論(要約)**: R-01〜R-10 は概ね適切に解消されている。静的・単体テスト範囲で新たな重大回帰は検出されなかったが、**案3(OpenSearch Security)は Docker 実行なしでは成否を確定できない箇所が複数**あり、うち 1 件(rag-api イメージのビルド時 CA コピー、N-01)は成立すれば plan3 のビルド自体を止める潜在リスクである。ユーザー決定(§8)には違反なし。Codex の変更には一切手を加えていない。

---

## 1. R-01〜R-10 判定サマリ

| ID | 主題 | 判定 | 重要度(残存) |
|---|---|---|---|
| R-01 | L1 評価指標(HitRate/MRR/nDCG/Evidence Recall/重複排除) | **解消済み** | — |
| R-02 | 評価コードが案2 rag-api の本番検索経路を利用 | **解消済み**(実接続は未確認) | 軽微 |
| R-03 | 3案の再取り込みを全量再構築へ統一 | **解消済み** | — |
| R-04 | Python 依存の固定と現行 API 整合 | **解消済み**(実 import 未確認) | 軽微 |
| R-05 | 要件文言調整・Open WebUI 維持・ライセンス記述 | **解消済み** | — |
| R-06 | OpenSearch Security・TLS・ユーザー権限・認証整合 | **一部解消 / 実行環境がなく未確認** | 重大(N-01)〜中(N-02) |
| R-07 | 再検索が別観点を生成・試行上限・状態遷移 | **解消済み** | — |
| R-08 | 固定IP/AMI削除順序/EICE削除待機/SSH説明 | **解消済み** | — |
| R-09 | 浮動タグ・依存のマイナー固定 | **解消済み** | — |
| R-10 | README/docs/deploy/test 間の記述ずれ | **解消済み** | — |

新規発見: **N-01(重大・未確認)/ N-02(中・未確認)/ N-03(軽微)/ N-04(軽微)**。

---

## 2. 重点項目の詳細

### R-01: L1 評価指標の計算 — 解消済み

- 根拠: [test/level1/run_level1.py:38-67](../test/level1/run_level1.py)
  - `matching_evidence()`(L38-45)は **quote 部分一致のみ**で加点し、`doc_id` は加点に使わない。R-01 の「同一法令の無関係チャンクがヒットになる」緩さを除去。
  - `score_ranking()`(L48-67):`covered` 集合で **同一 evidence の重複取得を二重加点しない**(L54)。`ideal_hits = min(evidence_count, k)`(L60)で **IDCG をゴールデン正解根拠数基準**に修正。`evidence_recall = len(covered)/evidence_count`(L64)を追加。
- 数値検証: [test/level1/test_run_level1.py](../test/level1/test_run_level1.py) 3 件 **PASS**。
  - `test_ndcg_uses_all_golden_evidence_for_idcg`: evidence 2 件中 1 件取得 → nDCG = `1/(1+1/log2(3))` ≈ **0.613**(旧実装の 1.000 過大評価を是正)。手計算一致を確認。
  - `test_doc_id_match_without_quote_is_not_a_hit`: doc_id 一致のみは非ヒット。
  - `test_duplicate_match_is_not_counted_twice`: 同一 evidence 重複取得で Evidence Recall=0.5 のまま。
- 実行コマンド: `python -m unittest test_run_level1 -v`(test/level1)→ `Ran 3 tests ... OK`
- 文書整合: [docs/evaluation-spec.md:43-46,82-83,155-170](../docs/evaluation-spec.md) が新指標定義・IDCG 定義・「quote のみで採点/doc_id は監査用」・目標表(HR@4/EvRecall@4/MRR@4)へ更新済み。実験管理表の列も 10 列へ拡張し、`run_level1.py:152` の出力行と列数が一致。
- 残存リスク: なし(実データ数値は未取得だが計算ロジックは確定)。

### R-02: 案2 rag-api の本番検索・rerank・NO_ANSWER 経路の利用 — 解消済み(実接続未確認)

- 根拠:
  - [deploy/plan2/rag-api/main.py:81-84](../deploy/plan2/rag-api/main.py) `retrieve_docs()` を新設し、本番 `chat_completions`(L154)と評価エンドポイントが**同一の MMR 検索 + rerank(しきい値付き)**を共有。
  - [deploy/plan2/rag-api/main.py:125-139](../deploy/plan2/rag-api/main.py) `/internal/evaluation/retrieve` が candidates(MMR）/ reranked / settings(retrieve_k, rerank_top_n, rerank_threshold)を返す。
  - [test/level1/run_level1.py:89-94](../test/level1/run_level1.py) 評価は同エンドポイントの返す実設定値(`rerank_top_n` 等)を final_k に使用。旧 Qdrant 直叩き・閾値なしを撤去。
  - [test/level2/run_level2.py:28-58](../test/level2/run_level2.py) 回答は本番 `/v1/chat/completions` を呼び、**NO_ANSWER 分岐・rerank 閾値・生成プロンプト**を rag-api 内で共有。旧 `PROMPT`/`embed`/`search`/`rerank` の複製を削除。
- 整合確認: 案2 `RERANK_TOP_N` 既定 = **4**([main.py:27](../deploy/plan2/rag-api/main.py))、案3 = **5**([plan3/main.py:31](../deploy/plan3/rag-api/main.py))。evaluation-spec.md:46 の「案2 既定 k=4 / 案3 既定 k=5」と一致。ラベルは `final_k` で動的表示。
- 残存リスク(軽微): 
  - **N-03 参照** — 評価エンドポイントの「localhost 専用」は未強制。
  - L2 は「採点用コンテキスト取得(`/internal/evaluation/retrieve`)」と「回答生成(`/v1/chat/completions`)」で **rag-api を 2 回叩く**。MMR は固定埋め込みで決定的なため通常一致するが、厳密な同一性は保証されない。procedure.md:65 に明記済みで許容範囲。
- 実接続(rag-api 起動・Qdrant・TEI)は Docker 不在のため未確認。

### R-03: 3案の全量再構築・危険な中間状態 — 解消済み

- 案1 [deploy/plan1/app/ingest.py:23-30](../deploy/plan1/app/ingest.py): `Chroma(...).delete_collection()` 後に `from_documents`。FORCE_RECREATE 分岐自体が無かった問題を解消。フレッシュな persist dir でも `Chroma()` が get-or-create するため `delete_collection()` は冪等(例外なし)。
- 案2 [deploy/plan2/rag-api/ingest.py:27](../deploy/plan2/rag-api/ingest.py): `force_recreate=True` に固定(環境変数依存を撤去)。
- 案3 [deploy/plan3/rag-api/ingest.py:24-32](../deploy/plan3/rag-api/ingest.py): `recreate_index()` が存在時削除 → 常に作成。`FORCE_RECREATE` 分岐を撤去。
- 危険な中間状態: いずれも「削除 → 再作成/再登録」の順で、失敗時は空/未完成インデックスが残るが**旧データとの重複は発生しない**。ドキュメントも「差分ファイルだけで実行しない・全コーパスを配置」を [docs/deployment-guide.md:77,164](../docs/deployment-guide.md)、[docs/plan2-standard.md:82](../docs/plan2-standard.md) に明記。
- 文書/実装整合: 案1 は in-process Chroma ハンドルが削除で無効化されるため、[deployment-guide.md:77,164](../docs/deployment-guide.md) が **案1 のみ `docker compose restart chainlit-app`** を指示。サービス名は [deploy/plan1/docker-compose.yml:4](../deploy/plan1/docker-compose.yml) の `chainlit-app` と一致。案2/3 はクライアントがインデックス名で毎回問い合わせるため再起動不要 — この案別の区別は正確。
- 残存 grep: `FORCE_RECREATE` 参照は deploy/docs/test から**消失**を確認。
- 残存リスク: なし(実行時の削除→再作成は Docker 未確認だが順序ロジックは妥当)。

### R-04 / R-09: 依存とコンテナタグの固定 — 解消済み(実 import 未確認)

- コンテナタグ(浮動タグ grep で `latest`/`:main`/`cpu-latest`/`opensearch:2` の**残存ゼロ**を確認):
  - `vllm/vllm-openai:v0.23.0`、`open-webui:v0.9.4`、`qdrant:v1.18.1`、`text-embeddings-inference:cpu-1.9.3`、`nginx:1.30.3`、`postgres:16.14`、`opensearchproject/opensearch:2.19.6`、`python:3.11-slim`。すべてマイナー系列以上に固定(R-09 決定「検証フェーズはマイナー固定」に合致)。
  - `docs/plan2-standard.md` のサンプル compose も同一タグへ更新。`vllm.service` の pip も `"vllm~=0.23.0"` に。plan1 Dockerfile は `"torch~=2.7.0"`。
- Python 依存: `deploy/plan{1,2,3}/*/requirements.txt` と新規 `test/level1/requirements.txt`・`test/level2/requirements.txt` すべて `~=`(マイナー固定)へ。旧「pip freeze で固定」コメントを撤去。
  - level2 は `ragas~=0.2.0` を明示し、[run_level2.py:9-10](../test/level2/run_level2.py) と procedure.md が「0.4 系へ上げる場合はコードも同時移行」を注記。R-04 の Ragas v0.4 非互換問題に対し **0.2 系固定 + 移行注意**で対処。
  - 案1/2/3 rag-api の `langchain*~=0.3.0`(v1 系ではない)により、R-04 の「LangChain v1 で `langchain.retrievers` が `langchain-classic` へ移動」問題を回避。plan1 app.py の該当 import は 0.3 系で成立する想定。
- ピン形式: `~=X.Y.Z` は PEP 440 準拠(`>=X.Y.Z,<X.(Y+1)`)で構文妥当。
- 残存リスク(軽微): 実際の `pip install` による依存解決・import は未実施。指定バージョンの相互整合(例: `langchain 0.3` × `langgraph 0.6` × `langchain-huggingface 0.3`)は静的には妥当だが、実ビルドで確定すべき。

### R-05: 要件文言・ライセンス — 解消済み

- [README.md:9](../README.md)・[agent/session.md:10](../agent/session.md) の「すべて(の)無償 OSS」→「**無償利用可・ソース公開**のソフトウェア」へ調整(ユーザー決定 (a))。
- ライセンス表([README.md:181](../README.md) 付近、「BSD-3 ベース(ブランディング条項付き)」)は現状維持で正確。Open WebUI 差し替えは行わず、決定どおり維持。
- 残存リスク: なし。

### R-06: OpenSearch Security / TLS / 権限 / 認証整合 — 一部解消・重要部分は実行環境なく未確認

**設計として整合が取れている点(静的確認):**

- `DISABLE_SECURITY_PLUGIN=true` を撤去し `OPENSEARCH_INITIAL_ADMIN_PASSWORD` を付与([docker-compose.yml:64-86](../deploy/plan3/docker-compose.yml))。deploy/docs から `DISABLE_SECURITY_PLUGIN` の**残存ゼロ**(review.md の履歴記述を除く)。
- [opensearch_client.py](../deploy/plan3/rag-api/opensearch_client.py): `use_ssl=True, verify_certs=True, ssl_assert_hostname=True, ca_certs=OS_CA_CERT`。`OPENSEARCH_URL` が https でなければ起動時エラー。username/password は env 由来。
- **初期管理者を不要なサービスへ渡していない**(重点確認項目):
  - `rag-api` は `OS_USERNAME=rag_api`/`OS_PASSWORD=${OS_RAG_PASSWORD}`([docker-compose.yml:46-47](../deploy/plan3/docker-compose.yml))。
  - `ingest` は `OS_USERNAME=ingest`/`OS_PASSWORD=${OS_INGEST_PASSWORD}`([:141-142](../deploy/plan3/docker-compose.yml))。
  - `OPENSEARCH_INITIAL_ADMIN_PASSWORD` を受け取るのは `opensearch` 本体と `security-init` のみ。**rag-api/ingest には渡っていない**ことを確認。`env_file: .env`(全変数注入)を撤去し個別 `environment:` に限定した点も適切。
- 最小権限: [init_security.py:31-52](../deploy/plan3/rag-api/init_security.py) が `rag_reader`(read + `indices:admin/exists`、cluster_monitor)/`rag_ingest`(indices_all)を作成し、`rag_api`/`ingest` ユーザーへ割当。検索専用・更新専用の分離は R-06 決定に合致。
- 起動順: `security-init` 完了(`service_completed_successfully`)後に rag-api / ingest が起動([:55-61,151-155](../deploy/plan3/docker-compose.yml))。`init_security` は自前で cluster health を最大 180 秒ポーリングし、接続失敗は `OpenSearchException`(ConnectionError 系を包含)で捕捉 → タイムアウト時 `SystemExit`。危険な中間状態は残さない。
- 証明書配布: rag-api イメージへ **公開 CA(root-ca.pem)のみ**をコピー(秘密鍵は非コピー)。デモ DNS alias `node-0.example.com` は OpenSearch デモ証明書の既知 SAN に一致させる意図で、`ssl_assert_hostname` と整合する設計。
- 文書整合: [deployment-guide.md:104-140](../docs/deployment-guide.md)・[plan3-hybrid.md](../docs/plan3-hybrid.md) が Security 有効化・security-init・別ユーザー・デモ CA の位置づけ・本番での組織 CA 置換を明記。旧「DISABLE_SECURITY_PLUGIN 無効の内部限定」注記は撤去。

**未確認・要 Docker(重点確認項目のうち実接続に依存する部分):** → **N-01・N-02** を参照。

### R-07: 再検索の別観点生成・試行上限・状態遷移 — 解消済み

- [query_rewrite.py](../deploy/plan3/rag-api/query_rewrite.py) `build_rewrite_prompt(question, previous_queries, attempt)`:試行回数と**検索済みクエリ(再利用禁止)**をプロンプトへ注入。`attempt < 1` で `ValueError`。
- [plan3/main.py:98-126](../deploy/plan3/rag-api/main.py): `RagState` に `previous_queries` を追加し、`node_retrieve` が毎回 `state["query"]` を履歴へ蓄積(L125)。`node_rewrite` は 2 回目以降に履歴付きプロンプトで書き換え(L110-114)。初期 state に `previous_queries: []`(L209)。
- 状態遷移: `route_grade`(L129-134)は docs あり→generate、`attempts <= MAX_RETRIES`→rewrite、超過→no_answer。`attempts` は `node_retrieve` で +1。初回(attempts=0)は元質問、以降 MAX_RETRIES(既定 2)まで再検索。上限ロジックに off-by-one なし(初回 + 最大 2 回再試行)。
- 単体テスト: [test/plan3/test_query_rewrite.py](../test/plan3/test_query_rewrite.py) 3 件 **PASS**(履歴反映・試行間でプロンプト変化・attempt≥1 検証)。`python -m unittest test_query_rewrite -v` → OK。
- 文書整合: [plan3-hybrid.md:66,124](../docs/plan3-hybrid.md) が「temperature 0 でも毎回同一プロンプトにはならない」旨に更新。図の「質問分解」誇張表現も「再検索ループ」へ是正。
- 残存リスク: なし(LLM の実出力の相違は実行検証対象外だが、プロンプト差分の生成は確定)。

### R-08: AWS 手順 — 解消済み

- ①固定IP: [node-a-pre-install.md:55-76](../docs/node-a-pre-install.md) に `--private-ip-address "${ip_llm}"`(=192.168.0.10)と user-data によるホスト名設定を追加。`aws-provisioning.md §1.3` と挙動整合。生成した user-data は `rm -v` で後始末(§4-1 の `-v` 規約遵守)。
- ②AMI/snapshot 削除順序: [aws-provisioning.md:511-518](../docs/aws-provisioning.md) で **deregister の前に** `describe-images` で `snap_id` を取得する順序へ修正。旧「deregister 後に取得(取得不能)」の矛盾を解消。
- ③EICE 削除待機: [aws-provisioning.md:482-491](../docs/aws-provisioning.md) に State ポーリングの `while` ループを追加(`delete-complete` で break、`delete-failed` で `exit 1`、その他 `sleep 10`)。SG 削除前に ENI 解放を待つ。
- ④SSH ホスト鍵: [aws-provisioning.md:289](../docs/aws-provisioning.md) の「EICE/IAM で保護済み」を、「ホスト鍵検証は代替しない/厳格運用では known_hosts 管理」へ適正化(決定=無効化受容・表現適正化のみ)。
- CLI 規約: 追加ブロックは `${var}` ブレース・`cat >` ヒアドキュメント・`rm -v` を遵守。`vim` 使用。while ループは複数行だが性質上妥当。
- 残存リスク: AWS CLI 実行は未実施(構文・順序の静的確認のみ)。

### R-10: 文書と実装の記述ずれ — 解消済み

- ①[deployment-guide.md:16](../docs/deployment-guide.md) 「Ubuntu Server 24.04 LTS」に統一(22.04 併記を撤去)。
- ②[README.md:145](../README.md) 比較表「デプロイ(Node B)= Docker Compose(venv+systemd は代替)」へ。[plan1-minimal.md:5,55](../docs/plan1-minimal.md) も標準=Docker へ。
- ③[plan3-hybrid.md:33-52](../docs/plan3-hybrid.md) 図から未実装の「取り込みジョブ管理/ジョブ状態→PostgreSQL」「ragapi→PG」を削除。
- ④[plan2-standard.md:82](../docs/plan2-standard.md) healthcheck 記述を「サンプル compose は未設定・運用時に設定」へ是正(compose に healthcheck を足さず文書側で整合)。
- ⑤[plan1-minimal.md:65-101](../docs/plan1-minimal.md) 説明コードを `build_embeddings()`(e5 prefix 自動付与)+ `delete_collection()` へ更新。素の `HuggingFaceEmbeddings` による黙示の精度劣化を解消。`pip install -r requirements.txt` へ集約。
- ⑥[agent/session.md:54](../agent/session.md) §4-4 に「systemd 等の非 shell 設定テンプレートの `<your-...>` と本文の `<type>` は適用外」を明文化(規約側の適用除外を追記)。
- 付随: [test/README.md](../test/README.md)・[test/cases/TC01_single_fact.md](../test/cases/TC01_single_fact.md)・[TEMPLATE.md](../test/cases/TEMPLATE.md)・[level1/procedure.md](../test/level1/procedure.md)・[level2/procedure.md](../test/level2/procedure.md) の指標名・前提サービス・doc_id 位置づけを新仕様へ更新。Markdown ローカルリンク 0 件破損・コードフェンス全ファイル均衡を確認。
- 残存リスク: なし。

---

## 3. 新規発見(Codex 修正により生じた/残った論点)

### N-01 — 【重大・実行環境がなく未確認】rag-api イメージのビルド時 CA コピーが OpenSearch イメージのビルド時ファイルに依存

- 箇所: [deploy/plan3/rag-api/Dockerfile:1-8](../deploy/plan3/rag-api/Dockerfile)
  ```
  FROM opensearchproject/opensearch:2.19.6 AS opensearch-certs
  ...
  COPY --from=opensearch-certs /usr/share/opensearch/config/root-ca.pem /app/certs/root-ca.pem
  ```
- 懸念: OpenSearch のデモ証明書(`root-ca.pem`, `esnode.pem` 等)は通常、**コンテナ起動時に entrypoint の `install_demo_configuration.sh` が生成/配置**するもので、**イメージのビルド時点で `config/root-ca.pem` が存在する保証がない**。存在しない場合、`docker build ./rag-api` が「COPY failed: no source files」で**失敗し、plan3 全体がビルド不能**になる。
- 影響: 成立すれば案3 の起動を完全に阻害する(=最も重い潜在回帰)。逆にビルド時に同ファイルが同梱されているイメージであれば問題なし。どちらであるかは**イメージ内部の実ファイル依存**で、静的には判定不能。
- 実行コマンド(未実施 / 要 Docker):
  - `docker run --rm --entrypoint ls opensearchproject/opensearch:2.19.6 config/ | grep root-ca.pem`(ビルド時同梱かの確認)
  - もしくは `docker build deploy/plan3/rag-api` の成否
- 残存リスク: 高。デモ証明書がランタイム生成であれば、ビルド段階で別ステージ生成(例: 一時起動して cp、または `opensearch-plugin`/`securityadmin` のデモ生成を build 内で実行)へ設計変更が必要。**必ず Docker で確認すべき最優先項目。**

### N-02 — 【中・実行環境がなく未確認】OpenSearch 最小権限・ホスト名/SAN・管理者 REST 権限の実効性

- 箇所: [init_security.py:31-52](../deploy/plan3/rag-api/init_security.py)、[opensearch_client.py:8-27](../deploy/plan3/rag-api/opensearch_client.py)、[plan3/main.py:203](../deploy/plan3/rag-api/main.py)
- 懸念(いずれも稼働クラスタなしでは確定不能):
  1. `rag_reader` の `allowed_actions: ["read", "indices:admin/exists"]` が rag-api の `os_client.indices.exists(INDEX)`(HEAD /index)を**実際に認可するか**。アクション名 `indices:admin/exists` が実在アクション/`read` グループ内包かが不確実で、外れると **readiness チェックが 403 → chat が常時 503**。
  2. デモ node 証明書の SAN が `node-0.example.com` を含み、`ssl_assert_hostname=True` のホスト名検証を通過するか(alias 名は既知 SAN に合わせた意図が見えるが実物照合は未実施)。
  3. デモ `admin` 内部ユーザーが `/_plugins/_security/api/*`(Security REST API)を呼べるか(`plugins.security.restapi.roles_enabled` にデモ admin の role が含まれる前提。通常のデモ構成では成立するが未検証)。
- 実行コマンド(未実施 / 要 Docker): `docker compose up -d --build` 後、`docker compose logs security-init`(終了コード 0)、`curl --cacert ... -u rag_api:... https://node-0.example.com:9200/knowledge`、rag-api `/health` と実チャットの疎通。
- 残存リスク: 中。設計は妥当だが、上記 3 点のいずれかが外れると案3 の検索/初期化が実行時に失敗する。

### N-03 — 【軽微】案2 評価エンドポイントの「localhost 専用」が未強制

- 箇所: [deploy/plan2/rag-api/main.py:125-139](../deploy/plan2/rag-api/main.py)(docstring「localhost からの評価専用」)
- 懸念: `/internal/evaluation/retrieve` に送信元制限の実装はなく、同一 Docker ネットワーク上の他コンテナ(open-webui 等)から到達可能。露出する情報は既存 `/v1/chat/completions` が返す文書内容の範囲内で**増分リスクは小さい**が、コメントが実挙動より強く保護を主張している(R-08-④で是正したのと同種の過大表現)。
- 残存リスク: 軽微。文言を実態に合わせるか、`127.0.0.1` バインドのポートのみで到達する旨に限定すると正確。

### N-04 — 【軽微】改行終端の欠落(整形)

- 箇所: [.env.example:41](../deploy/plan3/.env.example)、[docker-compose.yml:161](../deploy/plan3/docker-compose.yml)、[rag-api/Dockerfile:11](../deploy/plan3/rag-api/Dockerfile) が「No newline at end of file」。
- 影響: 機能影響なし。`git diff --check` はクリーン。整形上の指摘のみ。

---

## 4. 実施した検証コマンドと結果

| 検証 | コマンド | 結果 |
|---|---|---|
| 差分把握 | `git status --short --branch` / `git diff --stat` / `git diff --name-status` / `git diff` / `git ls-files --others --exclude-standard` | 変更 32 追跡 + 未追跡 7(うち 6 ファイル+1 ディレクトリ) |
| 未追跡全文確認 | 7 対象すべて Read で確認 | 完了 |
| Python AST | `python -m py_compile`(変更/新規 13 ファイル) | `ALL_COMPILED_OK` |
| 単体テスト | `python -m unittest test_run_level1 -v` / `test_query_rewrite -v` | **6 件 PASS** |
| JSON | `json.load(index-mapping.json)` | OK |
| JSONL | `golden_dataset.sample.jsonl` 10 行パース + answerable の quote 必須確認 | 10 行 OK / quote 欠落なし |
| 浮動タグ | `grep -rE "image:.*(:latest|:main|cpu-latest|opensearch:2\b)"` | **残存 0** |
| FROM タグ | `grep -rn "^FROM"` | 全て固定タグ |
| 旧フラグ残存 | `grep -rn "FORCE_RECREATE\|DISABLE_SECURITY_PLUGIN\|@5\|FINAL_K\|env_file"` | deploy/docs/test に残存なし(review.md の履歴記述を除く) |
| Markdown | コードフェンス均衡(変更 14 md)/ ローカルリンク(全 md) | 不均衡 0 / 破損リンク 0 |
| 空白/改行 | `git diff --check` | クリーン |
| requirements | `~=` マイナー固定・PEP440 構文・import 対応 | 静的に整合(実 import 未確認) |

**未実施(実行環境なし)**: Docker build/compose、OpenSearch Security REST/TLS 実接続、AWS CLI、pip 実 install/import、RAG 実データ評価、bash/shellcheck。

---

## 5. ユーザー決定(session.md §8 / review.md §4)の遵守確認

| 決定 | 遵守 | 根拠 |
|---|---|---|
| R-05=(a) 文言調整・Open WebUI 維持 | ○ | README.md:9 / session.md:10 調整、ライセンス表現維持 |
| R-06=(b) Security Plugin 有効化手順を正式追加 | ○(実効性は N-01/N-02 で未確認) | compose・init_security・opensearch_client・docs 更新 |
| R-08-④ ホスト鍵検証無効化を受容・表現適正化のみ | ○ | `StrictHostKeyChecking no` 維持、L289 表現のみ適正化 |
| R-09 検証フェーズはマイナー固定 | ○ | 全タグ・全 requirements をマイナー系列で固定(digest 未固定=決定どおり) |

違反なし。ノード命名・Ubuntu 24.04・EICE・固定IP 等の確定事項も覆されていない。

---

## 6. 完了確認

- `git diff --check`: **クリーン**(空白エラーなし)。
- `git status --short --branch`: 追跡変更 32 + 未追跡 7 は**レビュー開始時と同一**(Codex の変更に増減なし)。
- Codex の変更に**手を加えていない**(source/docs/test/config はいずれも未編集)。
- Claude Code が追加した変更は **`agent/regression-review.md` の 1 ファイルのみ**。
  - 補足: 検証中の `python -m py_compile` / `unittest` により `__pycache__`(git 無視対象)が生成された。追跡ツリーには影響せず、削除は auto-mode により拒否されたため放置(いずれも `.gitignore` 済み・再生成可能なバイトコード)。

コミットは作成していない。以上でレビューを終了する。

---
---

# N-01〜N-04 追試レビュー(Codex 追加修正の検証)

## 0. 追試のステータス

| 項目 | 内容 |
|---|---|
| ステータス | **検証完了(N-01〜N-04 の追加修正のみを追試。R-01〜R-10 の全面再レビューは実施せず、静的再確認のみ)** |
| レビュー対象 | Codex による N-01〜N-04 修正(未ステージ・未コミット) |
| 基準/HEAD | `dd6ab3d`(HEAD も同一。全変更は未コミット。作業ツリーを直接確認) |
| レビュアー | Claude Code(Opus 4.8)/ 2026-07-14 / Windows + git-bash・Python 3.12.10 |
| 追加根拠(公式) | OpenSearch demo 証明書の SAN・静的性(WebSearch/公式 issue・docs)、`read` 系権限と `indices:admin/get` に関する公式 issue |
| 未実施(実行環境なし) | Docker build/compose/cp・OpenSearch Security REST/TLS 実接続・実 import。Docker 依存項目は「確認済み」に**しない** |

**結論(要約)**: N-01・N-03・N-04 は妥当に対処された(N-01 の核心=ビルド時失敗の除去は静的に確定)。N-02 は **1 点(rag_reader の index 存在確認権限)に実行時破綻の蓋然性が高い残存懸念**があり、公式 issue の傍証から「`indices:admin/exists` では `indices.exists()` を認可できない可能性が高い」。Docker 不在のため確定はできないが、Codex が追加した確認手順(手順 8)が正にこれを検出する。前回作業ツリー(regression-review 上部)と比べ、Codex の変更に手を加えていない。追加は本ファイルのみ。

## 1. 判定サマリ

| ID | 主題 | 判定 | 重要度 |
|---|---|---|---|
| N-01 | ビルド時 CA 依存の除去・起動時 CA 取得への再設計 | **静的には解消・実行時未確認** | 重大→(静的部分は解消) |
| N-02 | OpenSearch 権限/SAN/管理者 REST の実効性 | **一部解消 / 実行時未確認**(#1 は残存懸念=中) | 中 |
| N-03 | 評価エンドポイント docstring の実態整合 | **解消済み** | 軽微 |
| N-04 | 3 ファイルの LF 終端 | **解消済み** | 軽微 |

---

## 2. N-01 — 【静的には解消・実行時未確認】ビルド時 CA コピーの撤去と起動時取得への再設計

**修正内容(作業ツリー実確認):**

- **Dockerfile のビルド時 CA 依存を完全撤去** — [deploy/plan3/rag-api/Dockerfile](../deploy/plan3/rag-api/Dockerfile) から `FROM opensearchproject/opensearch:2.19.6 AS opensearch-certs` と `COPY --from=opensearch-certs ... root-ca.pem` を削除。現在は `COPY common.py main.py ingest.py init_security.py opensearch_client.py query_rewrite.py ./` のみ。→ **N-01 の核心(ビルド不能リスク)は静的に解消。** `docker build ./rag-api` はもう OpenSearch イメージのビルド時ファイルに依存しない。
- **起動時取得へ変更** — [docs/deployment-guide.md §3 手順 4-5](../docs/deployment-guide.md):
  - 手順 4: `docker compose up -d --build opensearch`(opensearch だけ起動)→ `docker compose logs -f opensearch`(`started` 待ち)→ `mkdir -v -p rag-api/certs` → `docker compose cp opensearch:/usr/share/opensearch/config/root-ca.pem rag-api/certs/root-ca.pem`
  - 手順 5: `docker compose build` → `docker compose up -d`(残りを起動)
- **CA の読み取り専用 mount** — [docker-compose.yml](../deploy/plan3/docker-compose.yml) の `rag-api`・`security-init`・`ingest` の 3 サービスへ `./rag-api/certs/root-ca.pem:/app/certs/root-ca.pem:ro`(grep 一致 = **3**)。opensearch 本体・nginx・open-webui には mount なし(不要)。
- **.gitignore** — [.gitignore](../.gitignore) に `deploy/plan3/rag-api/certs/root-ca.pem` を追加。生成物のみを除外(ディレクトリ全体ではなく当該ファイル限定)。

**ユーザー指定チェック項目への回答:**

| 確認項目 | 判定 | 根拠 |
|---|---|---|
| root-ca.pem 起動時生成という公式ソース確認は妥当か | 妥当だが本修正の正しさには非依存 | demo 設定は entrypoint 実行時に config を配置する挙動が公式にも整合。**再設計は「稼働中コンテナから cp」するため、ビルド時に存在するか否かに関係なく成立**する。よって前提の厳密性は correctness に影響しない。ビルド時の実ファイル不在そのものは Docker 未実行のため未確認 |
| Dockerfile がビルド時 CA へ依存しなくなっているか | **解消済み(静的確定)** | multi-stage・COPY --from を撤去 |
| 起動→CA取得→3サービス起動の順序が成立するか | 静的に成立 | 手順 4 で CA をホストへ取得後、手順 5 の `up -d` で mount。順序は正しい |
| 3 サービスへ ro mount されているか | **○** | rag-api/security-init/ingest すべて `:ro`(grep=3) |
| .gitignore が生成 CA だけを除外しているか | **○** | 当該 1 ファイルのみを対象 |
| build/up で OpenSearch 再作成→CA 食い違いの可能性 | **低リスク(下記)/ 実行時未確認** | 後述 |
| イメージ変更・再作成時の CA 再取得手順 | **有り** | guide に「OpenSearch イメージ変更/コンテナ再作成時は手順 4 で同じコンテナから CA を再取得」を明記 |
| 秘密鍵・管理者資格情報が rag-api/ingest へ渡っていないか | **○** | mount は公開 CA(root-ca.pem)のみ=秘密鍵は非配布。`rag-api`=`rag_api`/`OS_RAG_PASSWORD`、`ingest`=`ingest`/`OS_INGEST_PASSWORD`。`OPENSEARCH_INITIAL_ADMIN_PASSWORD` は opensearch 本体と security-init だけが受領([docker-compose.yml:38-62,88-102,138-155](../deploy/plan3/docker-compose.yml)) |

**「docker compose build → up で OpenSearch が再作成され CA が食い違う」可能性の精査(ユーザー重点):**

- 手順 5 の `docker compose build` は `build:` を持つ全サービス(opensearch・rag-api・security-init・ingest は同一 ./rag-api イメージ)を再ビルドする。opensearch イメージ(`FROM opensearchproject/opensearch:2.19.6` + kuromoji install)はキャッシュヒットで**同一 image ID** となり、続く `docker compose up -d` は opensearch コンテナを**再作成しない**(compose は image/config 不変なら維持)。この正常経路では手順 4 で取得した CA と稼働ノード証明書は一致する。guide のコメント「手順 4 の OpenSearch コンテナは再作成しない」もこの前提を明示。
- **再作成が起こり得る唯一の経路**はビルドキャッシュ無効化等で opensearch の image ID が変わる場合。ただし OpenSearch の **demo 証明書は静的にバンドルされた固定ファイル**(公式 issue #3174 は「demo 証明書の SAN に `::1` が無い」という**固定証明書**のバグ報告であり、証明書がインスタンス毎に生成されないことを裏付ける。SAN=`node-0.example.com`/`localhost`/`127.0.0.1` は既知固定)。したがって仮に再作成されても **root-ca.pem は同一**で、取得済み CA との食い違いは生じない。
- 結論: **食い違いの実害は demo 証明書が固定であるため生じない。** 再作成の可能性自体はゼロではないが benign。よって「未解消」ではなく「静的には解消・実行時未確認」。念のため、完全に再作成を排除したい場合は手順 5 を `docker compose up -d --no-build`(手順 5 冒頭の `docker compose build` 後)にする選択肢もあるが、現行手順+固定証明書で実害はない。
- 実行時未確認(要 Docker): `docker compose cp` の実成功、config パスの実在、`build`+`up` が実際に opensearch を再作成しないこと、TLS ハンドシェイクの成立。

**残存リスク**: 低(静的部分は確定)。Docker 実行での end-to-end 確認が残る。

## 3. N-02 — 【一部解消 / 実行時未確認、#1 は残存懸念(中)】権限・SAN・管理者 REST

- **#2 SAN 一致 — 実質確認(公式)**: OpenSearch demo ノード証明書(esnode.pem)の SAN は **DNS:`node-0.example.com`, DNS:`localhost`, IP:`127.0.0.1`**([公式 issue #3174](https://github.com/opensearch-project/security/issues/3174)・[OpenSearch docs troubleshoot/tls](https://docs.opensearch.org/latest/troubleshoot/tls/))。compose の network alias `node-0.example.com` と一致するため、[opensearch_client.py](../deploy/plan3/rag-api/opensearch_client.py) の `ssl_assert_hostname=True` のホスト名検証は通る見込み。**alias 名の選定は妥当。**（実 TLS 接続は未確認)
- **#1 rag_reader の index 存在確認権限 — 残存懸念(中)/ 実行時未確認**:
  - [init_security.py:31-37](../deploy/plan3/rag-api/init_security.py) は `rag_reader` に `allowed_actions: ["read", "indices:admin/exists"]` を付与。
  - しかし [plan3/main.py:203](../deploy/plan3/rag-api/main.py) の `os_client.indices.exists(INDEX)` は **HEAD /{index}** を送り、OpenSearch 側では `GetIndexAction` = **`indices:admin/get`** で認可される。公式傍証([security issue #2120](https://github.com/opensearch-project/security/issues/2120)「特定 index の権限は `get` と `indices:data/read/search` を付けないと動かない」)は、既定 `read` グループが **`indices:admin/get` を含まない**ことを示唆する。
  - すなわち `indices:admin/exists`(2.x では実質レガシー/該当アクション無し)では **`indices.exists()` を認可できず 403**(`AuthorizationException`)になる蓋然性が高い。`indices.exists()` は 404→False を返すが **403 は送出**するため、[plan3/main.py:203](../deploy/plan3/rag-api/main.py) の readiness チェックで未捕捉例外 → **chat が 500 で常時失敗**しうる。
  - **推奨(参考、修正はユーザー/Codex 判断)**: `rag_reader` の `allowed_actions` へ `indices:admin/get`(または `get` アクショングループ)を追加する。
  - Docker 不在のため 2.19.6 実挙動での確定は不可。**Codex 追加の手順 8**(`docker compose exec rag-api python -c '... indices.exists ...'` が成功すること)が正にこの点を検出する検証であり、設置自体は適切。
- **#3 demo admin の Security REST 権限 — 未確認**: security-init は admin ユーザーで `/_plugins/_security/api/*` を PUT。demo 構成では admin が REST API 有効ロールに含まれる前提だが、実接続・終了コード 0 は Docker 不在で未確認。
- `rag_ingest`=`indices_all` は index 作成/削除/bulk を包含し、ingest の全量再構築([ingest.py:24-32](../deploy/plan3/rag-api/ingest.py))と整合。
- **deployment-guide の確認コマンドの整合**: 手順 6 は `docker compose exec opensearch bash -c 'curl --cacert config/root-ca.pem -u "admin:${OPENSEARCH_INITIAL_ADMIN_PASSWORD}" https://node-0.example.com:9200/...'`。opensearch コンテナ内では同 env 変数が定義され、`config/root-ca.pem` も実在(cwd=/usr/share/opensearch)。手順 8 の index 拒否確認・手順 9 の実検索も含め、確認手順は N-02 の各懸念に対応済み。**ただしいずれも Docker 実行が前提**で、本追試では実行していない。

**残存リスク**: 中。#1 は実行時に破綻する可能性が相対的に高く、最初の ingest/chat で表面化する。SAN(#2)は公式で裏取り済み。

## 4. N-03 — 【解消済み】評価エンドポイント docstring の実態整合

- [deploy/plan2/rag-api/main.py:126](../deploy/plan2/rag-api/main.py) の docstring を「**評価専用。認可は設けず、ホスト公開だけ Compose で 127.0.0.1 に限定する。**」へ修正。
- 実態と一致: エンドポイントに認可実装は無く(=「認可は設けず」正確)、ホスト公開は [plan2/docker-compose.yml:23](../deploy/plan2/docker-compose.yml) の `127.0.0.1:8000:8000` で限定(=「ホスト公開だけ 127.0.0.1 限定」正確)。同一 Docker ネットワークからの到達可能性を隠さない表現になった(R-08-④ と同種の過大表現を是正)。
- 評価手順への影響なし: パス・返却スキーマ・呼び出し側([run_level1.py:26-35](../test/level1/run_level1.py))は不変。
- 残存リスク: なし。

## 5. N-04 — 【解消済み】3 ファイルの LF 終端

- バイト検査(`open(...,"rb")`): `deploy/plan3/.env.example`・`deploy/plan3/docker-compose.yml`・`deploy/plan3/rag-api/Dockerfile` はいずれも **末尾 = 単一 `\n`(LF)**、CRLF は**ファイル内に一切なし**(`has_CRLF_anywhere=False`)。「No newline at end of file」は解消。
- **全体 CRLF 変換の非発生**: `git diff --name-only` の全変更ファイルを走査し、CRLF を含むファイルは **0 件**。過去の罠(Windows text モードでの LF→CRLF 全行 diff)は再発していない。
- `git diff --check`: クリーン。
- 残存リスク: なし。

---

## 6. 再実行した静的検証(追試)

| 検証 | 結果 |
|---|---|
| Python AST(`py_compile` 13 ファイル) | `ALL_COMPILED_OK` |
| 単体テスト(`test_run_level1` / `test_query_rewrite`) | **6 件 PASS** |
| JSON(index-mapping.json)/ JSONL(golden 10 行) | OK |
| 浮動タグ grep(`latest`/`main`/`cpu-latest`/`nginx:stable`/`qdrant:latest`/`opensearch:2`) | 実害 0(`postgres:16.14` は `16\b` 正規表現の誤検出で固定済み) |
| CA mount(`certs/root-ca.pem:...:ro`) | 3 サービス |
| Markdown コードフェンス均衡(変更 14 md)/ ローカルリンク(全 md) | 不均衡 0 / 破損 0 |
| LF 終端・CRLF 混入(N-04 + 全変更ファイル) | LF 終端 OK / CRLF 0 |
| `git diff --check` | クリーン |

**未実施(Docker 不在)**: `docker build`(rag-api / opensearch)・`docker compose up`・`docker compose cp`・OpenSearch Security REST/TLS 実接続・権限 403 の実挙動・実 import。→ **N-01 の end-to-end と N-02 #1/#3 は実行時未確認のまま。**

## 7. 差分の健全性(Codex 変更への非干渉)

- 前回追試(本ファイル上部)以降で Codex が変更したファイル: `.gitignore`(新規差分)・`deploy/plan3/docker-compose.yml`・`deploy/plan3/rag-api/Dockerfile`・`deploy/plan3/.env.example`・`docs/deployment-guide.md`・`deploy/plan2/rag-api/main.py`(docstring)・`agent/session.md`(§8 追記)。いずれも N-01〜N-04 に対応し、意図と一致。
- Claude Code は **source/docs/config/test を一切編集していない**(追加は `agent/regression-review.md` の本節のみ)。既存レビュー本文は削除・置換せず監査証跡として保持。
- 検証で生成される `__pycache__` は `.gitignore` 済み・追跡ツリー非影響。

## 8. コミット可否の最終報告

- N-01: **静的には解消・実行時未確認**(ビルド時失敗は確定的に除去。end-to-end は要 Docker)
- N-02: **一部解消 / 実行時未確認** — **#1(rag_reader の `indices.exists` 権限)は実行時に 403→chat 500 となる蓋然性が高い残存懸念**。手順 8 で検出可能。#2 SAN は公式で裏取り済み。
- N-03: **解消済み**
- N-04: **解消済み**

**コミット可否**: 文書・静的検証の範囲では健全でコミット可能な状態。ただし **N-02 #1 は Docker 検証(または `rag_reader` への `indices:admin/get` 追加検討)を経てからのコミットを推奨**。少なくとも案3 は初回 `docker compose up` + ingest + chat の実疎通(手順 6・8・9)で N-01 end-to-end と N-02 #1/#3 を実測するまで「未検証」を明示したままにすること。コミットは作成していない。

出典(N-01/N-02 の公式確認):
- [opensearch-project/security issue #3174(demo 証明書 SAN)](https://github.com/opensearch-project/security/issues/3174)
- [OpenSearch Docs — Troubleshoot TLS](https://docs.opensearch.org/latest/troubleshoot/tls/)
- [opensearch-project/security issue #2120(index 権限に get が必要)](https://github.com/opensearch-project/security/issues/2120)

---
---

# N-02 #1 最終追試(rag_reader 権限修正の確認)

> **この追記は、上記「3. N-02」および「8. コミット可否」で示した N-02 #1 の判定「一部解消 / 実行時未確認(残存懸念・中)」を更新するものである。** 既存記録は削除・書き換えず、本節を最新判定とする。

## 0. 対象と方法

| 項目 | 内容 |
|---|---|
| 対象 | Codex が推奨どおり `rag_reader` の `allowed_actions` を修正した 1 点のみ |
| 基準/HEAD | `dd6ab3d`(HEAD 同一、全変更は未コミット。作業ツリーを直接確認) |
| レビュアー | Claude Code(Opus 4.8)/ 2026-07-14 |
| 実施 | 該当ファイル現物確認、`opensearch-py` v2.8.0 公式ソース確認、Python 構文検証、`git diff --check` |
| 未実施(Docker 不在) | security-init の実 PUT、TLS 実接続、403/200 の実挙動 |

## 1. 変更内容(作業ツリー実確認)

[deploy/plan3/rag-api/init_security.py:31-37](../deploy/plan3/rag-api/init_security.py) の `rag_reader`:

```python
put(admin, "/_plugins/_security/api/roles/rag_reader", {
    "cluster_permissions": ["cluster_monitor"],
    "index_permissions": [{
        "index_patterns": [INDEX],
        "allowed_actions": ["read", "indices:admin/get"],   # ← indices:admin/exists から変更
    }],
})
```

前回指摘どおり `indices:admin/exists` → **`indices:admin/get`** へ置換されている。

## 2. ユーザー指定チェック項目への回答

| # | 確認項目 | 判定 | 根拠 |
|---|---|---|---|
| 1 | opensearch-py v2.8.0 の `indices.exists()` が `HEAD /{index}` を送るか | **確認(公式ソース)** | [opensearchpy/client/indices.py@v2.8.0](https://github.com/opensearch-project/opensearch-py/blob/v2.8.0/opensearchpy/client/indices.py) の `exists()` は `perform_request("HEAD", _make_path(index), ...)`。pin(`opensearch-py~=2.8.0`)とタグ一致 |
| 2 | OpenSearch 2.19.6 で同リクエストが `GetIndexAction.NAME = indices:admin/get` として認可されるか | **静的に妥当(実接続未確認)** | HEAD `/{index}` は `RestGetIndicesAction`(GET/HEAD 兼用)経由で `GetIndexAction`=`indices:admin/get`。「get-index に `indices:admin/get` が要る」旨は[公式 issue #2120](https://github.com/opensearch-project/security/issues/2120)とも整合。実 403/200 は Docker 不在で未確認 |
| 3 | `read` だけでは不足しうる点への `indices:admin/get` 明示追加が妥当か | **妥当** | 既定 `read` グループは data-read 中心で `indices:admin/get` を含まないため、明示追加が最小差分の正攻法。[main.py:203](../deploy/plan3/rag-api/main.py) の readiness チェック `os_client.indices.exists(INDEX)` に必要な権限を過不足なく付与 |
| 4 | rag_reader へ書き込み権限を追加していないか | **○(読み取り専用のまま)** | `["read", "indices:admin/get"]` はいずれも読み取り系。`cluster_permissions` は `cluster_monitor` のみ。index/create/write/delete 系は不在=検索専用を維持 |
| 5 | rag_ingest の `indices_all` や他 Security 設定を壊していないか | **○(不変)** | [init_security.py:38-52](../deploy/plan3/rag-api/init_security.py) の `rag_ingest`=`["indices_all"]`、`internalusers` の `rag_api`→`rag_reader`・`ingest`→`rag_ingest` の割当はいずれも変更なし。変更は rag_reader の 1 行のみ |
| 6 | session.md が「静的確認済み/Docker 実接続未確認」を正しく区別しているか | **○** | [agent/session.md:114](../agent/session.md) は、権限修正の根拠(HEAD→`indices:admin/get`)を記した上で、`rag_ingest`・admin REST を「静的確認済み」、`security-init` 終了コード 0・TLS 実接続・Security REST・health/実検索・更新可否を「Docker 不在のため未確認」と明確に分離 |

## 3. 静的検証(実行結果)

- `python -m py_compile`(init_security.py / opensearch_client.py / main.py / ingest.py)→ **COMPILE_OK**
- `git diff --check` → **クリーン**
- 変更は init_security.py の rag_reader 1 行のみで、他の Security 定義・呼び出し側([main.py:203](../deploy/plan3/rag-api/main.py))と整合。

## 4. 最終判定(N-02 #1)

**静的には解消・実行時未確認。**

- 前回の「残存懸念(中)」は解消方向へ更新: `indices.exists()`(HEAD /{index})が要求する `indices:admin/get` を rag_reader が明示的に保持したため、前回想定した「403 → chat 500」経路は**静的には塞がれた**。読み取り専用の性質も維持。
- 実接続(security-init の実 PUT 成功、rag_api ユーザーでの `indices.exists`=200、更新操作=403)は Docker 不在のため**未確認のまま**。Codex 追加の deployment-guide 手順 8 が実測の検証点。

## 5. コミット可否(最終報告)

- N-02 #1 は**静的には解消**。N-01(end-to-end)・N-02 #2/#3 の Docker 実測が残るが、これらは「実行時未確認」として文書に明示済みで、**静的・文書レビューの範囲ではコミット可能**な状態。
- 案3 を実運用へ進める前に、少なくとも `docker compose up`+ingest+chat の実疎通(手順 6・8・9)で TLS・権限 403/200・実検索を確認することを推奨する。
- Claude Code の変更は **`agent/regression-review.md` への本節追記のみ**。ソース・`agent/session.md`・ドキュメントは未編集。stage・commit は行っていない。
