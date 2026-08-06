# Docling VLM変換手順書

## 概要

コードはMITです。既定のGranite DoclingモデルはApache-2.0です。別モデルへ切り替える場合はモデルカードを再確認してください。

各ページを画像としてGranite Doclingへ入力します。L4 GPUを既定とし、標準パイプラインとは別結果として扱います。

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
python3 -m venv .venv-docling-vlm
source .venv-docling-vlm/bin/activate
python -m pip install --upgrade pip
python -m pip install 'docling[vlm]==2.*' pypdf psutil
python -m pip freeze > metrics/docling-vlm-versions.txt
```

GPUを使うプロダクトでは、次が `True` になることを確認します。PyTorchを使わない製品では製品固有の確認コマンドを優先します。

```bash
python -c 'import torch; print(torch.cuda.is_available(), torch.version.cuda)' || true
```

## サンプル変換の実行

```bash
source .venv-docling-vlm/bin/activate
.venv-docling-vlm/bin/python scripts/convert_docling_vlm.py
```

出力は `out/docling-vlm/<元ファイル名>.md`、メトリクスは `metrics/docling-vlm.csv` です。既存の空でないMarkdownはスキップします。

## 全件実行

比較手順書の選定基準を満たした場合だけ実行します。

```bash
source .venv-docling-vlm/bin/activate
.venv-docling-vlm/bin/python scripts/convert_docling_vlm.py --all
```

失敗原因を直して再変換する場合だけ `--force` を追加します。RAM 16 GBのため並列実行しません。大きいPDFでOOMが起きた場合は一時ディレクトリでページ分割し、順番に変換してから結合します。分割条件を結果へ記録します。

## メトリクス確認

```bash
column -s, -t metrics/docling-vlm.csv | less -S
python scripts/aggregate_metrics.py
```

`success=false`、空出力、VRAM 24 GB超過のおそれ、RAM不足を優先して調べます。RAMとVRAMは、変換プロセスとその子孫だけを0.5秒間隔で観測した近似値です。

## トラブルシューティング

- CUDA OOM時はGPU上の別プロセスを停止します。収まらない版ではSmolDoclingへ切り替え、モデル名を記録します。
- 数字と固有名詞を原本と照合し、VLMの生成誤りを確認します。

CLIが導入版と異なる場合は、既定値を直接編集せず、まず `.venv-docling-vlm/bin/python scripts/convert_docling_vlm.py --command '{input} を含むコマンド'` で1件を試します。動作確認後に版と変更理由を文書へ反映します。
