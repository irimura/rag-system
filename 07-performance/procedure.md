# Open WebUI 性能試験手順

> コマンド中の `${...}` は環境に合わせて置換してください。

- 目的: Open WebUI 経由で、ユーザー体感に近い非ストリーミング応答時間と失敗率を測定する
- 特徴: perf-001 から nginx の HTTPS エンドポイントへ負荷を与え、Open WebUI と後段の RAG / vLLM を含む経路全体を測定する
- 対象: 案1b、案2、案3。案1(Chainlit / app-001)は Open WebUI を使用しないため対象外

## 1. 前提条件

- [ ] 対象 Node B が起動済み
- [ ] Open WebUI の初回管理者登録が完了済み
- [ ] Open WebUI で API キーを発行済み
- [ ] 案1bではナレッジコレクションを作成し、測定対象モデルへ紐付け済み
- [ ] perf-001 セットアップ済み

## 2. 測定準備

### 2.1 API キーの発行

管理者端末から対象 Node B へ SSH LocalForward を開始します。案1b の例:

```bash
ssh -N ragsys-app-001b
```

- ブラウザで `https://localhost:8441` を開き、初回管理者でログインする
- 管理者設定で API キーの利用を有効化する
- `Settings` → `Account` で API キーを発行し、安全な場所へ控える

案2は `https://localhost:8442`、案3は `https://localhost:8443` に読み替えます。

### 2.2 案1bのナレッジ設定

案1bだけ、Open WebUI でナレッジコレクションを作成して文書を登録し、測定対象の vLLM モデルへ紐付けます。測定前に同じモデルを選択してチャットを 1 回実行し、登録文書に基づく回答が返ることを確認します。

### 2.3 perf-001 からの疎通確認

perf-001 でモデル一覧を取得し、応答に `${OWUI_MODEL}` が含まれることを確認します。自己署名証明書を使用するため `-k` で TLS 証明書検証を無効化します。

```bash
curl -sk https://${app_ip}/api/models -H "Authorization: Bearer ${OWUI_API_KEY}"
```

## 3. 実行手順

最初に測定条件を 1 箇所で定義します。以下は案1b の例です。

```bash
cd ${HOME}
source ${HOME}/locust-venv/bin/activate
app_ip=192.168.0.24
OWUI_API_KEY=${owui_api_key}
OWUI_MODEL=${vllm_model_name}
users=10
spawn_rate=1
duration=10m
result_prefix=results/performance-$(date +%Y%m%d-%H%M%S)
export OWUI_API_KEY OWUI_MODEL
mkdir -v -p results
```

### 3.1 Headless 実行

```bash
locust -f locustfile.py --headless -u ${users} -r ${spawn_rate} -t ${duration} --host https://${app_ip} --csv ${result_prefix}
```

出力例:

```text
Type     Name                    # reqs  # fails |  Avg  Min  Max  Med | req/s failures/s
POST     /api/chat/completions      120  0(0.00%) | 2450 1800 4100 2380 |  0.20       0.00
Aggregated                         120  0(0.00%) | 2450 1800 4100 2380 |  0.20       0.00
```

### 3.2 Web UI 実行

perf-001 で、§3 冒頭の変数を定義した同じシェルから起動します。

```bash
locust -f locustfile.py --host https://${app_ip}
```

管理者端末で `ssh -N ragsys-perf-001` を実行し、SSH LocalForward 8089 経由で http://localhost:8089 を開きます。ユーザー数、起動率、実行時間を入力して開始します。

`locustfile.py` の `wait_time` はユーザーの思考時間を模擬します。そのため RPS は概ね `users / (思考時間 + 応答時間)` で頭打ちになり、同時ユーザー数だけから一定の RPS を保証するものではありません。

## 4. 判定

応答時間は `stream: false` で回答全体を受信し終えるまでの**非ストリーミング総所要時間**です。同じコーパス、モデル、Node B 構成、同時ユーザー数、実行時間で比較します。RPS は思考時間と回答長の影響を受けるため参考値として記録します。

| 指標 | 初期目標 | 未達時の一次対応 |
|---|---|---|
| p50 応答時間 | 5 秒以下 | Open WebUI、RAG、vLLM のログと区間別時間を確認する |
| p95 応答時間 | 15 秒以下 | Node B / Node A の CPU、メモリ、GPU、キュー滞留を確認する |
| 失敗率 | 1% 未満 | Locust の失敗内容と nginx / Open WebUI / RAG / vLLM のログを突合する |

## 5. 記録

`07-performance/experiments.md`(なければヘッダごと作成)へ、1 測定につき 1 行を追記します。

```markdown
| 日付 | 対象案 | モデル | users | duration | p50 | p95 | 失敗率 | メモ |
|---|---|---|---:|---|---:|---:|---:|---|
| ${date} | ${plan} | ${OWUI_MODEL} | ${users} | ${duration} | ${p50_ms} ms | ${p95_ms} ms | ${failure_rate} | ${notes} |
```

生成された `${result_prefix}_stats.csv` などの CSV も測定条件と対応付けて保管します。

## 6. 測定後のクリーンアップ

負荷試験のリクエストごとに生成された会話履歴は Open WebUI の DB に蓄積されます。テスト専用ユーザーで Open WebUI にログインし、チャット履歴の一覧から負荷試験で生成された会話を削除してください。

- 本番利用者の履歴を誤って削除しないよう、性能試験にはテスト専用ユーザーと専用 API キーを使用する
- 履歴を残す場合は DB ボリュームが肥大するため、測定前後の使用量を確認して保管期間を決める
- API キーを今後使用しない場合は、テスト用ユーザーの設定から失効または削除する

## 7. 他の案への読み替え

本文は案1b(app-001b)を基準に記載しています。

| 案 | ホスト | `${app_ip}` | `${OWUI_MODEL}` | 備考 |
|---|---|---|---|---|
| 案1b | app-001b | `192.168.0.24` | vLLM のモデル名 | ナレッジコレクションのモデルへの紐付けが必須 |
| 案2 | app-002 | `192.168.0.22` | `knowledge-rag` | RAG API を Open WebUI のモデルとして使用 |
| 案3 | app-003 | `192.168.0.23` | `knowledge-rag` | RAG API を Open WebUI のモデルとして使用 |

案1(Chainlit / app-001)は Open WebUI を使用しないため、本性能試験の対象外です。
