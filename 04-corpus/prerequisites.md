# コーパス取り込みの事前準備

> 以降のコマンド例中の `${repo_dir}` はリポジトリの絶対パス、`${pdf_file}` は確認対象 PDF の絶対パスへ、実行前に置き換えてください。

## 1. Node B のディスク容量

次の値は、raw、前処理済みファイル、`documents/` のコピー、Vector DB、前処理一時領域を同じ Node B に置く場合の安全側の目安です。ダンプ日付、PDF数、チャンク長、埋め込み次元、コピー/シンボリックリンクで変動するため、実測値を記録して EBS を拡張してください。

| 段階 | 推奨空き容量 | 主な内訳 |
|---|---:|---|
| 動作確認 | 10GB以上 | 白書 PDF、法令 XML/Markdown、モデルキャッシュ、Vector DB |
| 精度評価 | 30〜50GB以上 | 上記 + IPA PDF + livedoor 7,367記事 + 再構築用余裕 |
| 負荷・規模試験(部分ダンプ) | 100GB以上 | 圧縮ダンプ、抽出テキスト、`documents/`、Vector DB、WikiExtractor一時領域 |
| 負荷・規模試験(全件) | 300〜500GB以上 | jawiki全件の raw/processed/index と再構築時のピーク。実施前に最新サイズから再見積もり |

標準手順はコピー配置です。processed と `documents/` の両方に同じ本文を保持する前提で容量を確保してください。

`symlink` はディスク節約用の任意オプションです。作成されるリンクは `${CORPUS_DIR}` 配下への絶対リンクのため、標準 compose の `./documents:/data/documents:ro` だけでは ingestコンテナから参照できません。使用する場合は `${CORPUS_DIR}` を移動しない固定パスに置き、`docker compose` を実行するシェルで次を実行します。

```bash
set -a && source ${repo_dir}/scripts/corpus/corpus.env && set +a
```

さらに、対象案の `docker-compose.yml` の ingestサービスへ次の2行目を追加し、ホストとコンテナで同じ絶対パスをマウントします。

```yaml
volumes:
  - ./documents:/data/documents:ro
  - ${CORPUS_DIR}:${CORPUS_DIR}:ro
```

この追加マウントを行わない場合は必ず `copy` を使用します。

```bash
df -h ${repo_dir}
du -sh ${repo_dir}/deploy/plan*/documents ${HOME}/rag-corpus
```

## 2. Python venv と依存パッケージ

```bash
sudo apt update
sudo apt install -y curl poppler-utils python3 python3-venv tar
cd ${repo_dir}
python3 -m venv .venv-corpus
source .venv-corpus/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r scripts/corpus/requirements.txt
test -f scripts/corpus/corpus.env || cp -v scripts/corpus/corpus.env.example scripts/corpus/corpus.env
vim scripts/corpus/corpus.env
```

WikiExtractorは `requirements.txt` の固定版を使います。Node Bでの初回実行前に `python3 -m wikiextractor.WikiExtractor --version` を確認してください。

## 3. ネットワーク要件と隔離運用

[AWS構築手順](../aws-provisioning.md) §2 の一時 NAT + IGW を作成し、次の取得作業だけ Node B の外向き通信を許可します。

- Ubuntuパッケージ、Python依存、コンテナイメージ、Embedding/Rerankモデルの初回取得
- e-Gov、総務省、IPA、ロンウイット、Wikimediaからのコーパス取得
- URL、ライセンス、配布条件の最終確認

取得、前処理、コンテナ起動確認、必要なら AMI 化まで完了したら、外部 IdP 用の常設 NAT が不要な構成では [AWS構築手順](../aws-provisioning.md) §2.2 に従って NAT、EIP、一時サブネット、IGWを削除します。EICEは NAT/IGWを経由しないため、隔離後も保守接続できます。

## 4. ライセンス確認チェックリスト

- [ ] e-Gov法令は法令名、法令番号、法令ID、e-Gov URLを保持する
- [ ] 情報通信白書、IPA、デジタル庁等の政府資料は発行元、資料名、URLを出典として記録する
- [ ] Wikipedia抽出物は記事名、元URL、CC BY-SA 4.0を保持する
- [ ] livedoorは各カテゴリの `LICENSE.txt` を保管し、CC BY-ND 2.1 JPの表示条件を確認する
- [ ] livedoor本文を書き換えない、要約を保存しない、社内評価用途に限定する
- [ ] livedoorのチャンク分割は検索内部処理だけに留め、原文、チャンク、Vector DB、評価成果物を再配布しない
- [ ] 配布元の条件が取得時点で変わっていないことを確認し、確認日を作業記録へ残す

## 5. 固定グループと認可設計

コーパス配置の第1階層は次の5値に固定します。

| グループ | 文書 | 段階 |
|---|---|---|
| `laws` | e-Gov法令 Markdown | 動作確認 |
| `whitepaper` | 情報通信白書 PDF | 動作確認 |
| `ipa` | IPA PDF | 精度評価 |
| `livedoor` | livedoor原文テキスト | 精度評価 |
| `wikipedia` | jawiki抽出テキスト | 負荷・規模試験 |

[OIDC認証・グループ認可設計](../auth-oidc.md) §9.1では、`documents/<group>/...` の第1階層が案2/3の `metadata.group` と OpenSearch DLS の認可キーです。したがって、コーパス種別の5値を案2/3の `auth/groups.json` の `groups` に登録し、検証ユーザーへ必要な組み合わせを割り当てます。空所属、未知グループ、`documents/` 直下ファイルは fail closed です。

```bash
cd ${repo_dir}/deploy/plan2
test -f auth/groups.json || cp -v auth/groups.example.json auth/groups.json
vim auth/groups.json
```

案3も同様に `deploy/plan3/auth/groups.json` を編集します。精度評価用の利用者には `laws` / `whitepaper` / `ipa` / `livedoor`、負荷試験用の利用者には必要に応じて `wikipedia` を追加します。越境試験用には単一グループだけを持つ利用者も残します。

案1bでは Open WebUI の Admin Panel で同名グループを作成し、グループごとに private Knowledge の read 権限を付与します。案1は現行サンプルにグループ認可がありませんが、案2/3へ移行できるよう同じディレクトリ構成を維持します。

配置前に直下ファイルがないことを確認します。

```bash
find ${repo_dir}/deploy/plan2/documents -maxdepth 1 -type f ! -name '.gitkeep' -print
```

1件でも表示された場合は ingest を実行せず、5グループのいずれかへ移動します。

## 6. 開始前チェック

- [ ] 対象案の `.env` と必要な `auth/groups.json` を準備した
- [ ] Node Bの空き容量が対象段階の目安を満たす
- [ ] 取得時だけ NAT/IGWを開通し、終了後の削除判断を決めた
- [ ] `scripts/corpus/corpus.env` の年度、URL、法令ID、Wikipedia条件を確認した
- [ ] livedoorの社内評価限定・改変禁止を作業者へ周知した
- [ ] 全量再構築中の検索停止/性能低下を許容できる時間帯を確保した
