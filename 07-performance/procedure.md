# Open WebUI 性能試験手順

> コマンド中の `${...}` は環境に合わせて置換してください。

- 目的: Open WebUI 経由で、TTFT、TPOT(ITL)、Output token throughput、Request throughput の 4 指標を測定する
- 特徴: perf-001 から nginx の HTTPS エンドポイントへストリーミング負荷を与え、Open WebUI と後段の RAG / vLLM を含む経路全体を測定する
- 対象: 案1b、案2、案3。案1(Chainlit / app-001)は Open WebUI を使用しないため対象外

## 1. 前提条件

- [ ] 対象 Node B が起動済み
- [ ] Open WebUI の初回管理者登録が完了済み
- [ ] Open WebUI で API キーを発行済み
- [ ] 案1bではナレッジコレクションを作成し、測定対象モデルへ紐付け済み
- [ ] 案3は本改修後の rag-api イメージで再デプロイ済み
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
POST     /api/chat/completions      120  0(0.00%) | 8210 4500 14200 7900 |  0.20       0.00
SSE      ttft                       120  0(0.00%) | 1450  900  2800 1380 |  0.20       0.00
SSE      tpot                       120  0(0.00%) |   45   30    80   42 |  0.20       0.00
SSE      tokens_per_s               120  0(0.00%) |   22   12    33   21 |  0.20       0.00
Aggregated                         480  0(0.00%) | 2430  30 14200 1150 |  0.80       0.00
```

`SSE tokens_per_s` 行の数値の単位は ms ではなく tokens/s です。

### 3.2 Web UI 実行

perf-001 で、§3 冒頭の変数を定義した同じシェルから起動します。

```bash
locust -f locustfile.py --host https://${app_ip}
```

管理者端末で `ssh -N ragsys-perf-001` を実行し、SSH LocalForward 8089 経由で http://localhost:8089 を開きます。ユーザー数、起動率、実行時間を入力して開始します。

`locustfile.py` の `wait_time` はユーザーの思考時間を模擬します。そのため req/s は概ね `users / (思考時間 + 総応答時間)` で頭打ちになり、同時ユーザー数だけから一定の req/s を保証するものではありません。

## 4. 判定

同じコーパス、モデル、Node B 構成、同時ユーザー数、実行時間で比較します。`SSE ttft`、`SSE tpot`、`SSE tokens_per_s` と、本体の `POST /api/chat/completions` を Locust の集計・CSV・Web UI で確認します。

| 指標 | 初期目標・扱い | 未達時の一次対応 |
|---|---|---|
| TTFT p95 | 3 秒以下を目安 | 検索、リランク、Open WebUI、vLLM の区間別時間を確認する |
| TPOT(ITL) p95 | 100 ms 以下を目安 | vLLM のキュー滞留、GPU 使用率、同時実行数を確認する |
| Output token throughput(tokens/s) | 高いほど良い。構成間で比較する | モデル、量子化方式、生成長、同時実行数を確認する |
| 総応答時間 p95 | 回答長を揃えて構成間で比較する | Node B / Node A の CPU、メモリ、GPU、キュー滞留を確認する |
| 失敗率 | 1% 未満 | Locust の失敗内容と nginx / Open WebUI / RAG / vLLM のログを突合する |
| Request throughput(req/s) | 参考値。Locust 標準値を使用する | 思考時間、総応答時間、同時ユーザー数を確認する |

トークン数は SSE のコンテンツチャンク数による近似値です(案2・案3では末尾の参考資料 footer が 1 チャンク含まれるため +1 の誤差があります)。また、ここで測る TTFT には RAG の検索・リランク時間が含まれるため、vLLM 単体の TTFT とは異なります。

任意のクロスチェックとして、`curl -s http://192.168.0.10:8080/metrics` の `vllm:` プレフィックスから、vLLM 単体の TTFT / TPOT ヒストグラムを参照できます。

## 5. 記録

`07-performance/experiments.md`(なければヘッダごと作成)へ、1 測定につき 1 行を追記します。

```markdown
| 日付 | 対象案 | モデル | users | duration | ttft_p95 | tpot_p95 | tokens_s | total_p95 | 失敗率 | req/s | メモ |
|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|---|
| ${date} | ${plan} | ${OWUI_MODEL} | ${users} | ${duration} | ${ttft_p95_ms} ms | ${tpot_p95_ms} ms | ${tokens_s} | ${total_p95_ms} ms | ${failure_rate} | ${requests_s} | ${notes} |
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
| 案1b | app-001b | `192.168.0.24` | vLLM のモデル名 | ナレッジコレクションの紐付け後、クライアント層でストリーミング測定可能 |
| 案2 | app-002 | `192.168.0.22` | `knowledge-rag` | RAG API のトークンストリーミングを測定可能 |
| 案3 | app-003 | `192.168.0.23` | `knowledge-rag` | 本改修後の RAG API でトークンストリーミングを測定可能 |

案1(Chainlit / app-001)は Open WebUI を使用しないため、本性能試験の対象外です。
