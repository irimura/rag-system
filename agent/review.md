# レビュー記録 — Codex 一次レビュー + Claude Code 独立検証

## 0. 文書ステータス

| 項目 | 内容 |
|---|---|
| ステータス | **検証完了**(Claude Code による独立検証済み) |
| 一次レビュー | Codex / 2026-07-13 / `main`(`de161d4`) |
| 検証 | Claude Code(Fable 5)/ **2026-07-13** / 検証時 HEAD = `de161d4`(作業ツリー: `AGENTS.md` にユーザー未コミット変更あり — 本検証では不変更) |
| 検証方法 | 静的検証(該当ファイル・行の突合)、stdlib のみの数値再現(nDCG / is_hit)、公式一次情報の取得(AWS 公式 / LangChain 公式 / Ragas 公式 / OpenSearch 公式ドキュメントリポジトリ / open-webui 公式 LICENSE / LangChain 公式ソース) |
| 未実施(一次レビューと同じ) | Docker イメージのビルド・起動、依存パッケージの実 import、AWS 上での CLI 実行、RAG の実データ評価 |
| 次フェーズ | **Codex による資料修正**(「確認済み」「一部確認」の指摘のみ)。ユーザー判断 4 点は **2026-07-13 に決定済み**(§4)— 全指摘の修正に着手可能 |

## 1. 判定サマリ

| ID | 一次主張(要約) | 一次判定 | **検証後判定** | **検証後重要度** | 判定変更 |
|---|---|---|---|---|---|
| R-01 | L1 評価指標が実際より高く出る(is_hit の doc_id 緩さ / IDCG / multi-hop) | 重大・未検証 | **確認済み** | 重大 | 未検証→確認済み。数値再現あり |
| R-02 | 評価コードが rag-api の検索経路を再現していない | 重大・未検証 | **確認済み** | 重大 | 未検証→確認済み |
| R-03 | 再取り込みで重複・残存チャンク | 重大・未検証 | **確認済み** | 重大 | 未検証→確認済み。plan1 は FORCE_RECREATE 自体が未実装という追加事実あり |
| R-04 | 未固定依存で LangChain v1 / Ragas 互換が壊れる | 重大・未検証 | **確認済み** | 重大 | 未検証→確認済み(公式移行ガイドで裏取り) |
| R-05 | 「すべて無償 OSS」と Open WebUI 現行ライセンスの不整合 | 重大・未検証 | **確認済み(事実)** | 重大(要件解釈次第で構成変更に波及) | **ユーザー判断が必要** |
| R-06 | 案3 で OpenSearch Security Plugin 無効化 | 重大・未検証 | **確認済み(事実)** | 重大(全社向けの既定としては) | **ユーザー判断が必要**。公式の警告 2 件を確認。「非推奨」の明文は未取得 |
| R-07 | 案3 の再検索が同じ書き換えを繰り返す | 中・未検証 | **確認済み** | 中 | 未検証→確認済み |
| R-08 | AWS 手順の実行・セキュリティ不整合(4 件) | 中・未検証 | **確認済み(①②③)/ 一部確認(④)** | 中 | ④はリポジトリ側も注記済みの受容可能なトレードオフだが表現が過大 |
| R-09 | バージョン固定方針が用途と不整合 | 中・未検証 | **確認済み(事実)** | 中 | 固定の程度は**ユーザー判断が必要** |
| R-10 | 文書と実装の記述ずれ(6 件) | 中・未検証 | **一部確認**(①〜⑤確認済み / ⑥は適用範囲の解釈差) | 中(①②⑤)/ 軽微(③④)/ ⑥は規約明文化で対処 | ⑥のみ実質「誤り寄り」 |

**誤りと判定した一次指摘はない。** ⑥(R-10)のみ、指摘対象が規約の適用範囲外(意図的判断)であり「ずれ」ではなく「規約側の明文化不足」と再解釈した。

## 2. 詳細検証

### R-01: Retrieval 評価指標が実際より高く出る — 確認済み(重大)

一次主張: `is_hit()` が doc_id 部分一致でもヒット扱い / IDCG が取得ヒット数基準 / multi-hop の根拠網羅を検証できない。

根拠(リポジトリ):
- `test/level1/run_level1.py:59-68` — `is_hit()` は quote 不一致でも `ev["doc_id"] in source`(L66)でヒット。**同一法令の無関係チャンクでもヒットになることをロジック再現で確認(True)**
- `test/level1/run_level1.py:80-82` — `ideal_hits = min(sum(hit_flags), FINAL_K) or 1`(L81)。IDCG が「実際に取得できたヒット数」基準
- `eval/golden_dataset.sample.jsonl` — TC02-001 / TC10-001 は evidence 2 件
- `docs/evaluation-spec.md:82` — doc_id 一致によるヒット判定は**仕様に明記済み**(実装バグではなく仕様自体の緩さ)。同 `:43` の HitRate 定義「1 つでも含まれる」も同様
- `docs/evaluation-spec.md:45` — nDCG は「正解が複数ある場合の順位品質」を測ると定義しており、**現実装の IDCG はこの定義を満たさない**(こちらは仕様と実装の乖離)

数値再現(stdlib のみ、2026-07-13 実施):

```
evidence=2 件、うち 1 件のみ 1 位で取得 → 現行実装 nDCG = 1.000 / 正しい二値 nDCG = 0.613
evidence=2 件、2 件を 1・2 位で取得       → 両者 1.000(完全取得時は一致)
同一法令の quote 不一致チャンク            → is_hit = True
```

訂正・補足: doc_id フォールバックと HitRate の「1 件でも」判定は仕様どおりであり、修正は「実装修正」ではなく**評価仕様の厳格化**(例: doc_id 一致の廃止または補助指標化、IDCG をゴールデンデータの正解根拠数 `min(len(evidence), K)` 基準へ、multi-hop 用に evidence 網羅率(Recall)の追加)として行うべき。

### R-02: 評価コードが案2 rag-api の検索経路を再現していない — 確認済み(重大)

根拠(行対比):

| 項目 | rag-api(`deploy/plan2/rag-api/main.py`) | 評価コード |
|---|---|---|
| 検索方式 | `search_type="mmr", fetch_k=RETRIEVE_K*3`(L65) | Qdrant REST `points/search` の単純上位 K(`test/level1/run_level1.py:45`) |
| rerank 閾値 | `if r["score"] >= RERANK_THRESHOLD`(L78) | 閾値なし(`test/level1/run_level1.py:56`) |
| 空ヒット時 | `if not docs:` → LLM を呼ばず NO_ANSWER(L71, L127) | 空でも `generate_answer()` を呼ぶ(`test/level2/run_level2.py:57-59`) |

「同一ロジック」と記載している箇所: `test/level2/procedure.md:38,65`、`test/level2/run_level2.py:4`。**プロンプトの同一性(run_level2.py:29)のみ正しく、検索経路の同一性は不正確。**

訂正・補足: 評価の意味が「rag-api の性能評価」ではなく「別実装の性能評価」になっており、L1 合格→L2 という関門設計の前提を弱める。修正方向は (a) 評価スクリプトを rag-api と同一経路に揃える、または (b) rag-api に検索デバッグエンドポイントを設けて評価から直接叩く、のいずれか。

### R-03: 再取り込みで重複・残存チャンク — 確認済み(重大)

根拠:
- `deploy/plan1/app/ingest.py:22` — `Chroma.from_documents()` を ID 指定なしで再実行。**FORCE_RECREATE 相当の分岐が plan1 には存在しない**(一次レビュー未指摘の追加事実)
- `deploy/plan2/rag-api/ingest.py:22-27` — ID 指定なし。`force_recreate` は任意(既定 0)
- `deploy/plan3/rag-api/ingest.py:43-57` — bulk actions に `_id` なし(自動 ID)。`ensure_index` は FORCE_RECREATE 時のみ削除
- `docs/deployment-guide.md:143` — 「文書の追加・再取り込み」で通常の ingest 再実行を案内(このパスで既存文書分が重複する)
- LangChain Qdrant の既定 ID: **公式ソースで uuid4 を確認** — `ids_iterator = iter(ids or [uuid.uuid4().hex for _ in iter(texts)])`(langchain-ai/langchain `libs/partners/qdrant/langchain_qdrant/qdrant.py`、2026-07-13 取得)
- LangChain Chroma の既定 ID: **公式ソースで uuid4 を確認**(2026-07-13、ユーザーが公式リポジトリで確認)— ID 未指定時は `uuid.uuid4()` で生成(langchain-ai/langchain `libs/partners/chroma/langchain_chroma/vectorstores.py`)。さらに `RecursiveCharacterTextSplitter.split_documents()` は元 `Document.id` を新チャンクへ引き継がず(`libs/text-splitters/langchain_text_splitters/base.py`)、`deploy/plan1/app/common.py:39` 周辺でも独自 ID を設定していないため、**案1 の再取り込みは同一文書でも毎回新規 UUID となり重複が確定**する

訂正・補足: 更新・削除文書の既存チャンク削除処理が 3 案とも存在しない点も主張どおり。実害の出ない運用は現状 FORCE_RECREATE=1 の全再構築のみ(plan1 は volume 削除が必要)。修正方向: 安定 ID(原文書パス+チャンク連番等)の付与、または「再取り込みは常に全再構築」と運用を明記。

### R-04: 未固定依存により LangChain / Ragas 互換が再現できない — 確認済み(重大)

根拠:
- `deploy/plan1/app/requirements.txt` — 全行未固定(先頭コメントは「動作確認後は pip freeze で固定すること」)。`deploy/plan1/app/app.py` は `from langchain.retrievers import ContextualCompressionRetriever` / `langchain.retrievers.document_compressors` を import
- **LangChain v1 公式移行ガイド**(https://docs.langchain.com/oss/python/migrate/langchain-v1、2026-07-13 取得): 旧 `langchain.retrievers` を含む Retrievers・legacy chains 等は **`langchain-classic` へ移動**。v1 の `langchain` を新規インストールすると plan1 の import は成立しない
- **Ragas 公式 v0.3→v0.4 移行ガイド**(https://docs.ragas.io/en/stable/howtos/migrations/migrate_from_v03_to_v04/、2026-07-13 取得): 現行系列は **v0.4**。`evaluate()` は廃止(`@experiment()` へ)、メトリクス import は `ragas.metrics.collections` へ変更。`test/level2/run_level2.py`(`from ragas import evaluate` / `from ragas.metrics import faithfulness` — 0.2 系想定と自己申告 L11-12)は**最新版インストールでは動作しない**
- `test/level2/procedure.md` の「インストール後に `pip freeze`」は、導入時点の最新版とコードの互換性を保証しない(主張どおり)

訂正・補足: 主張どおり。修正方向: 動作可能な上限付き固定(例: `langchain<1` 系の明記、`ragas==0.2.x` 等)を requirements に直接記載するか、コードを現行版 API へ更新して固定する。コンテナタグは R-09 で扱う。

### R-05: 「すべて無償 OSS」と Open WebUI 現行ライセンス — 確認済み(事実)/ ユーザー判断が必要(重大)

根拠:
- **公式 LICENSE**(https://raw.githubusercontent.com/open-webui/open-webui/main/LICENSE、2026-07-13 取得): BSD-3 ベース + **第 4 条ブランディング保持条項**(名称・ロゴの改変制限。例外: 30 日間 50 ユーザー以下 / 書面同意 / エンタープライズライセンス)。追加制限付きのため OSI 定義のオープンソースには該当しない構成(docs.openwebui.com/license/ は 403 で本文未取得のため「OSI 非承認」の公式明文そのものは未確認だが、LICENSE 本文の追加制限で実質は判断可能)
- `README.md:181` — ライセンス表は「BSD-3 ベース(ブランディング条項付き。無償利用可)」と**既に開示済み**(この記述自体は正確)
- `README.md:9` / `agent/session.md:10` — 「**すべて無償 OSS**」の要件表現が残る

訂正・補足: 矛盾は「ライセンス表」ではなく**要件文言**にある。無償利用・ソース公開は継続しており、ブランディング非改変で使う本設計では実利用上の支障はない。**ユーザー判断**: (a) 要件文言を「無償で利用できる OSS/ソース公開ソフトウェア」等へ緩和して現構成を維持、(b) 厳密な OSI 準拠を要件とし WebUI を差し替え(候補検討が必要)。

**→ ユーザー決定(2026-07-13): (a) を採用**(§4 参照)。

### R-06: 案3 の OpenSearch Security Plugin 無効化 — 確認済み(事実)/ ユーザー判断が必要(重大)

根拠:
- `deploy/plan3/docker-compose.yml:44` 付近 — `DISABLE_SECURITY_PLUGIN=true`(コメントで「内部ネットワーク限定運用。外部公開時は必ず有効化する」と開示済み)。`docs/deployment-guide.md` §3 にも同旨の注記あり
- 同一 Docker ネットワーク上のコンテナ(open-webui / rag-api / TEI / nginx / postgres / ingest)からは 9200 へ**無認証で到達可能**(compose のネットワーク構成から静的に確認)
- **OpenSearch 公式**(documentation-website `_security/configuration/disable-enable-security.md`、2026-07-13 取得)の警告: 「Disabling or removing the plugin exposes the configuration index for the Security plugin. If the index contains sensitive information, make sure to protect it through some other means」「Disabling, removing, or installing the Security plugin requires a full cluster restart」。※「本番では非推奨」というそのものの明文は取得できたページ内には無し(この 1 点のみ**未確認**)

訂正・補足: 「127.0.0.1 限定で外部からは不可・コンテナ間は無認証」という現状把握は正確で、リポジトリも開示済み。争点は「全社利用向け」の既定として許容するか。**ユーザー判断**: (a) 内部ネットワーク境界+ホスト隔離で受容(現状維持+文書の位置づけ明確化)、(b) Security Plugin 有効化(証明書・初期パスワード・rag-api の認証対応を含む手順追加)。

**→ ユーザー決定(2026-07-13): (b) を採用**(§4 参照。修正フェーズの主要作業項目)。

### R-07: 案3 の再検索が同じ書き換えを繰り返す — 確認済み(中)

根拠: `deploy/plan3/rag-api/main.py:110-113` — 再試行時も `REWRITE_PROMPT.format(question=state["question"])` のみで、前回クエリ・失敗文脈を渡さない。`main.py:56` — `temperature=0`。よって 2 回目以降の書き換えは初回と同一になりやすく、`MAX_RETRIES`(L32/L127)分の再検索が同じクエリの反復になる蓋然性が高い。

訂正・補足: 主張どおり。厳密には LLM 出力の完全同一性は実行検証していない(温度 0 でも同一性は保証まではされない)が、「別観点で再検索」という文書(`docs/plan3-hybrid.md`)の意図を実装が満たさない点は確定。修正方向: 書き換えプロンプトへ試行回数と前回クエリを渡し「前回と異なる観点で」と明示する。

### R-08: AWS 手順の実行・セキュリティ上の不整合 — ①②③確認済み / ④一部確認(中)

1. **確認済み** — `docs/node-a-pre-install.md` §3.2 の `run-instances` に `--private-ip-address` がない(該当ブロックに `private-ip` 出現なしを grep で確認)。確定事項の固定 IP `192.168.0.10`(`agent/session.md:42`)と不整合。補足: 同ブロックはホスト名設定の user-data も省いており、`docs/aws-provisioning.md` §1.3 の `launch_node` と挙動差がある
2. **確認済み** — `docs/aws-provisioning.md:507-508` — `deregister-image` の後に `describe-images` で snap_id を取得する順序。直後のコメント(L509)自身が取得不能と説明しており、手順として実行不能。deregister の**前**に snap_id を取得する順序へ修正が必要
3. **確認済み(補足あり)** — `docs/aws-provisioning.md:483-491` — EICE 削除(L483)→ State 確認は非ブロッキングなコメント+単発コマンド(L484-485)のみで、SG 削除(L490-491)まで待機ループがない。ブロックを一括実行すると ENI 解放前の削除で失敗し得る。State ポーリングのループ化(または削除完了までの明示の手動ゲート)が必要
4. **一部確認** — `docs/aws-provisioning.md:251,289` — `StrictHostKeyChecking no` / `UserKnownHostsFile /dev/null` はホスト鍵検証を無効化する(事実)。「接続は EICE/IAM で保護済み」(L289)は、EICE が IAM 認可済みトンネルで**指定 instance-id へ**接続する点では妥当だが、ホスト鍵検証が担う「接続先ホストの成り済まし・侵害検知」を代替するものではなく、表現として過大。リポジトリは「厳格運用なら外す」と選択肢も開示済み。対処は表現の適正化(トレードオフの明記)で足りるが、受容可否は R-06 と同様に**ユーザー判断**でもよい

   **→ ユーザー決定(2026-07-13): 無効化を受容(現状維持)**。残タスクは L289 の表現適正化のみ(§4 参照)

参考(公式): EICE の SG 設計は AWS 公式(https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/eice-security-groups.html、2026-07-13 取得)の推奨(インスタンス SG のインバウンドは「送信元 = エンドポイント SG、ポート 22」、client IP preservation off 時の送信元はエンドポイント ENI)と本リポジトリの実装(`docs/aws-provisioning.md` §1.4)が一致することを確認。

### R-09: バージョン固定方針が用途と整合していない — 確認済み(事実)/ 固定の程度はユーザー判断(中)

根拠(2026-07-13 時点の grep 全数調査):

```
vllm/vllm-openai:latest(node-a) / open-webui:main(plan2,3) / qdrant:latest(plan2)
text-embeddings-inference:cpu-latest(plan2,3 ×4) / nginx:stable / postgres:16
opensearchproject/opensearch:2 / python:3.11-slim(×3)
requirements.txt: 3 ファイルとも全行未固定(コメントで freeze を案内)
```

訂正・補足: 事実は主張どおり。「オフライン AMI へ焼き込み、NAT 削除後は再取得しない」方針(`agent/session.md` §3)では、**AMI 化した時点の版が事実上固定される**ため定常運用は再現するが、(a) ノード再構築・AMI 作り直し時に別版が入る、(b) 評価の再現性(R-04)——の 2 点で未固定が問題になる。一律 digest 固定が正解とは限らない、という一次レビューの留保も妥当。**ユーザー判断**: 固定の程度(タグのメジャー/マイナー固定、digest 固定、requirements の完全固定)と更新運用。

**→ ユーザー決定(2026-07-13): 検証フェーズはマイナーバージョンまで固定。最終方針は運用設計フェーズで確定**(§4 参照)。

### R-10: ドキュメントと実装の記述ずれ — ①〜⑤確認済み / ⑥一部確認

1. **確認済み** — `docs/deployment-guide.md:17`「Ubuntu Server 22.04 / 24.04」併記。確定事項(24.04、`agent/session.md:22`)へ統一が必要(中)
2. **確認済み** — `README.md:145` 比較表「デプロイ(Node B)| venv + systemd」。正は Docker(`docs/plan1-minimal.md:7` は Docker 版を正と明記済み)。表の更新漏れ(中)
3. **確認済み** — `docs/plan3-hybrid.md:36,60` 図の「取り込みジョブ管理/ジョブ状態 → PostgreSQL」に対応する実装が `deploy/plan3/rag-api/ingest.py` に存在しない(軽微: 図の将来構想と現実装の区別を明記すれば足りる)
4. **確認済み** — `docs/plan2-standard.md:138`「healthcheck に設定」に対し `deploy/plan2/docker-compose.yml` に healthcheck 定義なし(grep 一致 0)。文書を「設定を推奨」に直すか compose に追加するかの二択(軽微)
5. **確認済み** — `docs/plan1-minimal.md:84,103` の説明コードは素の `HuggingFaceEmbeddings` で e5 を使用(プレフィックスなし)。実装 `deploy/plan1/app/common.py` は `E5Embeddings` で自動付与。**文書のコードをそのまま使うと検索精度が黙って劣化する**ため、説明コードにも prefix 対応(または common.py 参照)を明記すべき(中)
6. **一部確認** — `deploy/node-a/vllm.service:14-15,20` に `<your-hf-model>` 等が存在するのは事実。ただし §規約(`agent/session.md` §4-4)の適用対象は「手順書のコマンドライン」であり、systemd unit は配布テンプレート(過去ターンで対象外と明示判断済み。また systemd の `${VAR}` は `Environment=` 由来の展開で bash と意味が異なるため `<foo>` が実務上妥当)。`docs/aws-provisioning.md:454` の `<type>` は文中の説明表現。**「ずれ」ではなく規約側に適用除外の明文がないことが原因**。対処は `agent/session.md` §4 への除外規定の追記(軽微)

## 3. 一次レビュー §4「妥当と判断した事項」の独立確認

| 事項 | 検証結果 | 根拠 |
|---|---|---|
| G6e: L40S 48GB、xlarge 4vCPU/32GiB、2xlarge 8vCPU/64GiB | **確認済み** | AWS 公式 https://aws.amazon.com/ec2/instance-types/g6e/(2026-07-13 取得)。`docs/node-specs.md` §1.3 と一致 |
| DLAMI(Ubuntu 24.04)の G6e / CUDA 12.8 / Container Toolkit | **確認済み** | 公式リリースノート(gpubaseoss-ul2404 20260123): supported instances に G6e、NVIDIA Driver 580.126.09、CUDA スタックに /usr/local/cuda-12.8、nvidia_container_toolkit 1.18.1、docker-compose-plugin 同梱 |
| EICE 用 SG → インスタンス SG 22/tcp 許可の設計 | **確認済み** | AWS 公式 eice-security-groups(上記 R-08 参照)。`--no-preserve-client-ip` 時の送信元がエンドポイント ENI である点も一致 |
| OpenSearch RRF `score-ranker-processor` | **確認済み(2.19 導入)** | 公式ドキュメントソース `_search-plugins/search-pipelines/score-ranker-processor.md`(Introduced 2.19) |
| `knn_vector` + Lucene HNSW + `cosinesimil` | **未確認** | 公式ページ本文が取得経路の制約で確認できず(docs サイトは本文切り詰め、docs リポジトリの該当ファイルパス特定に失敗)。将来の検証: 公式ドキュメント該当ページの手動確認、またはローカル OpenSearch コンテナへ `index-mapping.json` を PUT して受理を確認 |

## 4. ユーザー判断項目 — **決定済み(2026-07-13)**

| ID | 決めること | 選択肢 | **決定** |
|---|---|---|---|
| R-05 | 「すべて無償 OSS」という要件文言の扱い | (a) 文言を「無償利用可・ソース公開」へ調整し現構成維持 / (b) OSI 準拠を厳守し WebUI 差し替え | **(a)** — 要件文言を調整し、Open WebUI を維持する(修正対象: `README.md:9` と `agent/session.md` の「すべて無償 OSS」表現。ライセンス表の記述は現状のまま正確) |
| R-06 | 案3 の Security Plugin 無効化の受容 | (a) 内部境界で受容(位置づけを文書で明確化)/ (b) 有効化手順を正式追加 | **(b)** — Security Plugin を有効化する手順を正式追加する(`deploy/plan3/` の compose・設定変更、証明書・初期管理者パスワード、rag-api / ingest の OpenSearch クライアント認証対応、`docs/plan3-hybrid.md`・`docs/deployment-guide.md` §3 の手順更新を含む) |
| R-08-④ | ホスト鍵検証無効化の扱い | (a) 表現の適正化のみ / (b) known_hosts 運用へ変更 | **無効化を受容(現状維持)** — `StrictHostKeyChecking no` は維持し、残タスクは「接続は EICE/IAM で保護済み」という過大表現の適正化(軽微)のみ |
| R-09 | バージョン固定の程度 | タグのマイナー固定 / digest 固定 / requirements 完全固定 / 現状維持 | **検証フェーズはマイナーバージョンまで固定**(コンテナタグ・Python 依存とも)。digest 固定等の最終方針は**運用設計フェーズで確定**する |

## 5. 検証メタデータ

- 検証日: 2026-07-13 / 検証者: Claude Code(Fable 5)/ 検証時 HEAD: `de161d4` / 環境: Windows + git-bash(静的検証・stdlib 再現のみ。依存導入・コンテナ起動・AWS 操作なし)
- 実行した主な検証コマンド:
  - `git status --short --branch`(作業ツリー確認)
  - `grep -n` による該当行の特定(run_level1.py / run_level2.py / plan2 main.py / 各 ingest.py / plan3 main.py / docs 各所 / compose・Dockerfile のタグ全数)
  - `python`(stdlib のみ)で `run_level1.py` L59-68・L77-87 のロジックを再現し nDCG 過大評価と is_hit 誤ヒットを数値確認
  - `python -c json` で `eval/golden_dataset.sample.jsonl` の evidence 数を確認
  - WebFetch(公式のみ): docs.langchain.com(v1 移行)/ docs.ragas.io(v0.3→v0.4)/ raw.githubusercontent.com の open-webui LICENSE・langchain qdrant.py・opensearch documentation-website(disable-enable-security.md, score-ranker-processor.md)/ docs.aws.amazon.com(eice-security-groups, DLAMI gpubaseoss-ul2404-2026-01-27)/ aws.amazon.com(G6e)
  - 取得失敗(未確認扱いの根拠): docs.openwebui.com/license(403)、OpenSearch docs サイト本文(切り詰め)、knn-vector 系 md のリポジトリパス(404)
  - 後続確認(2026-07-13): langchain-chroma ソースは検証セッション中断後にユーザーが公式リポジトリ(langchain-ai/langchain)で確認し、Chroma 既定 ID = uuid4・splitter の ID 非引き継ぎを確定(R-03 に反映済み)

## 6. 判定変更履歴(監査用)

- 全 10 件: 「未検証」→ 上記判定へ(2026-07-13、Claude Code)。重要度は R-01〜R-09 で一次レビューから変更なし。R-10 は内訳を細分化(①②⑤=中、③④⑥=軽微)し、⑥を「文書と実装のずれ」から「規約の適用除外が未明文化」へ再解釈
- R-03 内の Chroma 既定 ID の一次ソース確認: 未確認 → **確認済み**(2026-07-13、ユーザーが LangChain 公式リポジトリで確認。R-03 の総合判定「確認済み・重大」は変わらず、根拠が補強された)
- 2026-07-13: ユーザー判断 4 点(R-05 / R-06 / R-08-④ / R-09)が決定され §4 に記録。修正フェーズの着手条件が整った
- 一次レビューの §4「妥当と判断した事項」5 件中 4 件を独立確認、1 件(knn_vector/lucene/cosinesimil)は未確認のまま次フェーズへ持ち越し
