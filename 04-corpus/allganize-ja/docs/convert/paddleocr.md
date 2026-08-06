# PaddleOCR PP-StructureV3変換手順書

## 概要

PaddleOCRはApache-2.0です。PaddlePaddleのCUDA対応表と、取得した各モデルの条件も保存してください。

PP-StructureV3をL4 GPUで実行し、向き補正と日本語OCRを使います。

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
python3 -m venv .venv-paddleocr
source .venv-paddleocr/bin/activate
python -m pip install --upgrade pip
python -m pip install paddlepaddle-gpu paddleocr pypdf psutil
python -m pip freeze > metrics/paddleocr-versions.txt
```

GPUを使うプロダクトでは、次が `True` になることを確認します。PyTorchを使わない製品では製品固有の確認コマンドを優先します。

```bash
python -c 'import torch; print(torch.cuda.is_available(), torch.version.cuda)' || true
```

## サンプル変換の実行

```bash
source .venv-paddleocr/bin/activate
.venv-paddleocr/bin/python scripts/convert_paddleocr.py
```

出力は `out/paddleocr/<元ファイル名>.md`、メトリクスは `metrics/paddleocr.csv` です。既存の空でないMarkdownはスキップします。

## 全件実行

比較手順書の選定基準を満たした場合だけ実行します。

```bash
source .venv-paddleocr/bin/activate
.venv-paddleocr/bin/python scripts/convert_paddleocr.py --all
```

失敗原因を直して再変換する場合だけ `--force` を追加します。RAM 16 GBのため並列実行しません。大きいPDFでOOMが起きた場合は一時ディレクトリでページ分割し、順番に変換してから結合します。分割条件を結果へ記録します。

## メトリクス確認

```bash
column -s, -t metrics/paddleocr.csv | less -S
python scripts/aggregate_metrics.py
```

`success=false`、空出力、VRAM 24 GB超過のおそれ、RAM不足を優先して調べます。RAMとVRAMは、変換プロセスとその子孫だけを0.5秒間隔で観測した近似値です。

## トラブルシューティング

- `--device gpu` が認識されない場合はCLIヘルプとインストール版を確認します。
- 日本語モデルが自動選択されない場合は、その版の公式モデル名を明示します。
- RAM不足時は解像度を下げる前に1ページずつ処理します。

CLIが導入版と異なる場合は、既定値を直接編集せず、まず `.venv-paddleocr/bin/python scripts/convert_paddleocr.py --command '{input} を含むコマンド'` で1件を試します。動作確認後に版と変更理由を文書へ反映します。
