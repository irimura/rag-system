# YomiToku変換手順書

## 概要

**警告:** CC BY-NC-SA 4.0のため商用利用できません。組織内評価が非商用条件を満たすか確認できるまで実行しないでください。

日本語文書画像、縦書き、表を対象とするOCR枠です。

## 前提条件

Node A（Ubuntu 24.04、Python 3.11以上、NVIDIA L4 24 GB、RAM 16 GB）で実行します。シェル変数を使うコマンドは、実行前に値を確認してください。

```bash
cd 04-corpus/allganize-ja
nvidia-smi
python3 --version
df -h .
```

`sample_list.csv`、`pdfs/`、共通依存の `pypdf` が必要です。モデル取得中だけ外部接続を許可し、取得後は版とライセンスを記録します。

## インストール

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-dev build-essential poppler-utils
python3 -m venv .venv-yomitoku
source .venv-yomitoku/bin/activate
python -m pip install --upgrade pip
python -m pip install yomitoku pypdf psutil
python -m pip freeze > metrics/yomitoku-versions.txt
```

GPUを使うプロダクトでは、次が `True` になることを確認します。PyTorchを使わない製品では製品固有の確認コマンドを優先します。

```bash
python -c 'import torch; print(torch.cuda.is_available(), torch.version.cuda)' || true
```

## サンプル変換の実行

```bash
source .venv-yomitoku/bin/activate
.venv-yomitoku/bin/python scripts/convert_yomitoku.py
```

出力は `out/yomitoku/<元ファイル名>.md`、メトリクスは `metrics/yomitoku.csv` です。既存の空でないMarkdownはスキップします。

## 全件実行

比較手順書の選定基準を満たした場合だけ実行します。

```bash
source .venv-yomitoku/bin/activate
.venv-yomitoku/bin/python scripts/convert_yomitoku.py --all
```

失敗原因を直して再変換する場合だけ `--force` を追加します。RAM 16 GBのため並列実行しません。大きいPDFでOOMが起きた場合は一時ディレクトリでページ分割し、順番に変換してから結合します。分割条件を結果へ記録します。

## メトリクス確認

```bash
column -s, -t metrics/yomitoku.csv | less -S
python scripts/aggregate_metrics.py
```

`success=false`、空出力、VRAM 24 GB超過のおそれ、RAM不足を優先して調べます。RAMとVRAMは、変換プロセスとその子孫だけを0.5秒間隔で観測した近似値です。

## トラブルシューティング

- CLI引数が版と異なる場合は `yomitoku --help` を正として `--command` で上書きします。
- CUDA OOM時はバッチサイズ1とページ単位入力を使います。
- 条件未確認なら「未実行（ライセンス）」と記録します。

CLIが導入版と異なる場合は、既定値を直接編集せず、まず `.venv-yomitoku/bin/python scripts/convert_yomitoku.py --command '{input} を含むコマンド'` で1件を試します。動作確認後に版と変更理由を文書へ反映します。
