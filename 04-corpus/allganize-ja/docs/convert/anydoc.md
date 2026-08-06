# AnyDoc変換手順書

## 概要

AnyDocはMITです。OCRを持たず、画像のみのPDFは仕様上未対応です。スキャンPDFの代替には使いません。

文字埋込みPDFの高速基準です。GPUは使いません。pip版のPython APIである `anydoc.to_markdown()` を共通変換ラッパーから呼びます。npm版CLIは必要ありません。

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
python3 -m venv .venv-anydoc
source .venv-anydoc/bin/activate
python -m pip install --upgrade pip
python -m pip install firecrawl-anydoc pypdf psutil
python -c 'import anydoc; assert callable(anydoc.to_markdown)'
python -m pip freeze > metrics/anydoc-versions.txt
```

GPUを使うプロダクトでは、次が `True` になることを確認します。PyTorchを使わない製品では製品固有の確認コマンドを優先します。

```bash
python -c 'import torch; print(torch.cuda.is_available(), torch.version.cuda)' || true
```

## サンプル変換の実行

```bash
source .venv-anydoc/bin/activate
.venv-anydoc/bin/python scripts/convert_anydoc.py
```

出力は `out/anydoc/<元ファイル名>.md`、メトリクスは `metrics/anydoc.csv` です。既存の空でないMarkdownはスキップします。

## 全件実行

比較手順書の選定基準を満たした場合だけ実行します。

```bash
source .venv-anydoc/bin/activate
.venv-anydoc/bin/python scripts/convert_anydoc.py --all
```

失敗原因を直して再変換する場合だけ `--force` を追加します。RAM 16 GBのため並列実行しません。大きいPDFでOOMが起きた場合は一時ディレクトリでページ分割し、順番に変換してから結合します。分割条件を結果へ記録します。

## メトリクス確認

```bash
column -s, -t metrics/anydoc.csv | less -S
python scripts/aggregate_metrics.py
```

`success=false`、空出力、VRAM 24 GB超過のおそれ、RAM不足を優先して調べます。RAMとVRAMは、変換プロセスとその子孫だけを0.5秒間隔で観測した近似値です。

## トラブルシューティング

- `anydoc.to_markdown` がない場合は、インストールした配布物が `firecrawl-anydoc` かを確認します。
- `Unsupported` が画像のみPDFで出るのは仕様どおりです。成功扱いに変更しません。
- 暗号化PDFは復号権限を確認します。

Python APIが導入版と異なる場合は、既定値を直接編集せず、`--command` で1件を試します。動作確認後に版と変更理由を文書へ反映します。
