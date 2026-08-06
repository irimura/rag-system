# Marker変換手順書

## 概要

**警告:** コードはGPL-3.0、モデル重みは修正AI Pubs OpenRAIL-Mです。研究・個人利用や公式が定める規模未満の企業以外は、商用ライセンスの要否を確認してください。

L4 GPUを既定にし、複数プロセスを無効にして1文書ずつ変換します。

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
python3 -m venv .venv-marker
source .venv-marker/bin/activate
python -m pip install --upgrade pip
python -m pip install 'marker-pdf[full]' pypdf psutil
python -m pip freeze > metrics/marker-versions.txt
```

GPUを使うプロダクトでは、次が `True` になることを確認します。PyTorchを使わない製品では製品固有の確認コマンドを優先します。

```bash
python -c 'import torch; print(torch.cuda.is_available(), torch.version.cuda)' || true
```

## サンプル変換の実行

```bash
source .venv-marker/bin/activate
.venv-marker/bin/python scripts/convert_marker.py
```

出力は `out/marker/<元ファイル名>.md`、メトリクスは `metrics/marker.csv` です。既存の空でないMarkdownはスキップします。

## 全件実行

比較手順書の選定基準を満たした場合だけ実行します。

```bash
source .venv-marker/bin/activate
.venv-marker/bin/python scripts/convert_marker.py --all
```

失敗原因を直して再変換する場合だけ `--force` を追加します。RAM 16 GBのため並列実行しません。大きいPDFでOOMが起きた場合は一時ディレクトリでページ分割し、順番に変換してから結合します。分割条件を結果へ記録します。

## メトリクス確認

```bash
column -s, -t metrics/marker.csv | less -S
python scripts/aggregate_metrics.py
```

`success=false`、空出力、VRAM 24 GB超過のおそれ、RAM不足を優先して調べます。RAMとVRAMは、変換プロセスとその子孫だけを0.5秒間隔で観測した近似値です。

## トラブルシューティング

- CUDA OOM時はGPU上の別プロセスを停止し、複数プロセスが無効か確認します。
- モデル取得後にウォームアップしてから計測します。
- 無償条件を満たさない場合は実行しません。

CLIが導入版と異なる場合は、既定値を直接編集せず、まず `.venv-marker/bin/python scripts/convert_marker.py --command '{input} を含むコマンド'` で1件を試します。動作確認後に版と変更理由を文書へ反映します。
