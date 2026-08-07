# PDF変換プロダクト一括インストール手順書

## 1. 目的と実行方針

9プロダクトの実行環境をNode Aへ順番に導入する。共通OSパッケージは1回だけ導入し、Pythonパッケージはプロダクトごとのvenvへ分離する。

この段階では一括スクリプトを作らない。次の理由から、節ごとに結果を確認して進める。

- MinerU、YomiToku、Markerには利用条件の確認が必要である。
- NDLOCRはUbuntu 24.04およびPython 3.11との互換性を確認する必要がある。
- GPU向けパッケージは、CUDAとの不整合を製品ごとに切り分ける必要がある。
- モデル取得に失敗したとき、成功済みのvenvを作り直さずに再開できる。

`source` によるvenvの切り替えは使わない。最初にactivate済みのvenvを解除して基準Pythonの絶対パスを固定する。以後は `.venv-*/bin/python` またはvenv内のCLIを直接指定する。ただし、OSパッケージ、NVIDIAドライバー、GPU、RAM、モデルキャッシュ、シェル環境変数は共有される。

## 2. 実行前の停止条件

次の条件を満たさないプロダクトは、その節を実行せず「保留」と記録する。他のプロダクトの導入は続けてよい。

| プロダクト | 停止条件 |
|---|---|
| MinerU | AGPL-3.0の条件を想定用途で満たせるか未確認 |
| YomiToku | CC BY-NC-SA 4.0の非商用条件を満たすか未確認 |
| Marker | コードとモデル重みの利用条件を満たすか未確認 |
| NDLOCR | Python 3.11で公式依存を解決できない |

ライセンスの根拠と各プロダクトの適用範囲は、先に[製品説明資料](products.md)で確認する。

## 3. Node Aと空き容量の確認

リポジトリの配置先が異なる場合は、実行前に `${repo_dir}` を置き換える。

```bash
repo_dir=${HOME}/rag-system
cd "${repo_dir}/04-corpus/allganize-ja"
if [ -n "${VIRTUAL_ENV:-}" ]; then deactivate; fi
base_python=$(command -v python3)
"${base_python}" --version
nvidia-smi
df -h .
free -h
```

`${base_python}` がvenv配下ではなく、Python 3.11以上であることを確認する。`nvidia-smi` ではNVIDIA L4 24 GBと、ドライバーがCUDA 12系をサポートすることを確認する。各venvが実際に使うCUDA runtimeは、後続のPyTorchまたはPaddlePaddleの確認コマンドで判定する。モデルとvenvの合計がgp3 150 GBへ収まるよう、導入前後の空き容量を記録する。olmOCRだけでも公式要件として30 GB以上の空き容量が必要である。

## 4. 共通OSパッケージ

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-dev build-essential poppler-utils git
mkdir -pv metrics vendor
```

OSパッケージの導入はこの1回だけでよい。各venvへ入れる `pypdf` と `psutil` は、共通変換ラッパーのページ数・RAM・VRAM計測に使う。

## 5. CPU・標準パイプライン系

### 5.1 AnyDoc

```bash
(
set -e
: "${base_python:?先に3節で基準Pythonを設定してください}"
rm -fv .venv-anydoc/.install-complete
"${base_python}" -m venv .venv-anydoc
.venv-anydoc/bin/python -m pip install --upgrade pip
.venv-anydoc/bin/python -m pip install firecrawl-anydoc pypdf psutil
.venv-anydoc/bin/python -m pip check
.venv-anydoc/bin/python -c 'import anydoc; assert callable(anydoc.to_markdown)'
freeze_output=$(.venv-anydoc/bin/python -m pip freeze)
cat > metrics/anydoc-versions.txt <<EOF
${freeze_output}
EOF
touch .venv-anydoc/.install-complete
)
```

AnyDocはOCRを持たないため、文字埋込みPDFだけに使う。pip版ではCLIの有無に依存せず、共通変換ラッパーから `anydoc.to_markdown()` を呼ぶ。

### 5.2 Docling標準パイプライン

```bash
(
set -e
: "${base_python:?先に3節で基準Pythonを設定してください}"
rm -fv .venv-docling/.install-complete
"${base_python}" -m venv .venv-docling
.venv-docling/bin/python -m pip install --upgrade pip
.venv-docling/bin/python -m pip install 'docling==2.*' pypdf psutil
.venv-docling/bin/python -m pip check
.venv-docling/bin/docling --help
freeze_output=$(.venv-docling/bin/python -m pip freeze)
cat > metrics/docling-versions.txt <<EOF
${freeze_output}
EOF
touch .venv-docling/.install-complete
)
```

### 5.3 MinerU

AGPL-3.0の条件を確認できた場合だけ実行する。

```bash
(
set -e
: "${base_python:?先に3節で基準Pythonを設定してください}"
rm -fv .venv-mineru/.install-complete
"${base_python}" -m venv .venv-mineru
.venv-mineru/bin/python -m pip install --upgrade pip
.venv-mineru/bin/python -m pip install 'mineru[pipeline]>=3,<4' pypdf psutil 'six==1.17.0' 'cryptography==49.0.0'
.venv-mineru/bin/python -m pip check
.venv-mineru/bin/mineru-models-download
.venv-mineru/bin/mineru --help
freeze_output=$(.venv-mineru/bin/python -m pip freeze)
cat > metrics/mineru-versions.txt <<EOF
${freeze_output}
EOF
touch .venv-mineru/.install-complete
)
```

`mineru-models-download` が存在しない場合は、その版の公式手順を確認してモデルを取得する。別名のコマンドを推測して実行しない。

## 6. GPU・VLM系

GPU系はパッケージを導入した後、各venvでCUDAを確認する。同時に変換を実行しない。

### 6.1 Docling VLM

```bash
(
set -e
: "${base_python:?先に3節で基準Pythonを設定してください}"
rm -fv .venv-docling-vlm/.install-complete
"${base_python}" -m venv .venv-docling-vlm
.venv-docling-vlm/bin/python -m pip install --upgrade pip
.venv-docling-vlm/bin/python -m pip install 'docling[vlm]==2.*' pypdf psutil
.venv-docling-vlm/bin/python -m pip check
.venv-docling-vlm/bin/python -c 'import sys, torch; available = torch.cuda.is_available(); print(available, torch.version.cuda); sys.exit(0 if available else 1)'
.venv-docling-vlm/bin/docling --help
freeze_output=$(.venv-docling-vlm/bin/python -m pip freeze)
cat > metrics/docling-vlm-versions.txt <<EOF
${freeze_output}
EOF
touch .venv-docling-vlm/.install-complete
)
```

### 6.2 PaddleOCR PP-StructureV3

```bash
(
set -e
: "${base_python:?先に3節で基準Pythonを設定してください}"
rm -fv .venv-paddleocr/.install-complete
"${base_python}" -m venv .venv-paddleocr
.venv-paddleocr/bin/python -m pip install --upgrade pip
.venv-paddleocr/bin/python -m pip install paddlepaddle-gpu paddleocr pypdf psutil
.venv-paddleocr/bin/python -m pip check
.venv-paddleocr/bin/python -c 'import sys, paddle; available = paddle.device.is_compiled_with_cuda(); print(available, paddle.device.get_device()); sys.exit(0 if available else 1)'
.venv-paddleocr/bin/paddleocr --help
freeze_output=$(.venv-paddleocr/bin/python -m pip freeze)
cat > metrics/paddleocr-versions.txt <<EOF
${freeze_output}
EOF
touch .venv-paddleocr/.install-complete
)
```

### 6.3 olmOCR

```bash
(
set -e
: "${base_python:?先に3節で基準Pythonを設定してください}"
rm -fv .venv-olmocr/.install-complete
"${base_python}" -m venv .venv-olmocr
.venv-olmocr/bin/python -m pip install --upgrade pip
.venv-olmocr/bin/python -m pip install 'olmocr[gpu]' --extra-index-url https://download.pytorch.org/whl/cu128
.venv-olmocr/bin/python -m pip install pypdf psutil
.venv-olmocr/bin/python -m pip check
.venv-olmocr/bin/python -c 'import sys, torch; available = torch.cuda.is_available(); print(available, torch.version.cuda); sys.exit(0 if available else 1)'
.venv-olmocr/bin/python -m olmocr.pipeline --help
freeze_output=$(.venv-olmocr/bin/python -m pip freeze)
cat > metrics/olmocr-versions.txt <<EOF
${freeze_output}
EOF
touch .venv-olmocr/.install-complete
)
```

### 6.4 Marker

コードとモデル重みの条件を確認できた場合だけ実行する。

```bash
(
set -e
: "${base_python:?先に3節で基準Pythonを設定してください}"
rm -fv .venv-marker/.install-complete
"${base_python}" -m venv .venv-marker
.venv-marker/bin/python -m pip install --upgrade pip
.venv-marker/bin/python -m pip install 'marker-pdf[full]' pypdf psutil
.venv-marker/bin/python -m pip check
.venv-marker/bin/python -c 'import sys, torch; available = torch.cuda.is_available(); print(available, torch.version.cuda); sys.exit(0 if available else 1)'
.venv-marker/bin/marker_single --help
freeze_output=$(.venv-marker/bin/python -m pip freeze)
cat > metrics/marker-versions.txt <<EOF
${freeze_output}
EOF
touch .venv-marker/.install-complete
)
```

## 7. 日本語特化OCR系

### 7.1 YomiToku

非商用条件を満たすと確認できた場合だけ実行する。

```bash
(
set -e
: "${base_python:?先に3節で基準Pythonを設定してください}"
rm -fv .venv-yomitoku/.install-complete
"${base_python}" -m venv .venv-yomitoku
.venv-yomitoku/bin/python -m pip install --upgrade pip
.venv-yomitoku/bin/python -m pip install yomitoku pypdf psutil
.venv-yomitoku/bin/python -m pip check
.venv-yomitoku/bin/python -c 'import sys, torch; available = torch.cuda.is_available(); print(available, torch.version.cuda); sys.exit(0 if available else 1)'
.venv-yomitoku/bin/yomitoku --help
freeze_output=$(.venv-yomitoku/bin/python -m pip freeze)
cat > metrics/yomitoku-versions.txt <<EOF
${freeze_output}
EOF
touch .venv-yomitoku/.install-complete
)
```

### 7.2 NDLOCR

NDLOCRは最後に導入する。依存解決に失敗しても、ほかの8個のvenvには影響しない。

```bash
(
set -e
: "${base_python:?先に3節で基準Pythonを設定してください}"
rm -fv .venv-ndlocr/.install-complete
if [ ! -d vendor/ndlocr_cli/.git ]; then git clone https://github.com/ndl-lab/ndlocr_cli.git vendor/ndlocr_cli; fi
"${base_python}" -m venv .venv-ndlocr
.venv-ndlocr/bin/python -m pip install --upgrade pip
.venv-ndlocr/bin/python -m pip install -r vendor/ndlocr_cli/requirements.txt
.venv-ndlocr/bin/python -m pip install pypdf psutil
.venv-ndlocr/bin/python -m pip check
[ -f vendor/ndlocr_cli/src/ocr.py ]
freeze_output=$(.venv-ndlocr/bin/python -m pip freeze)
cat > metrics/ndlocr-versions.txt <<EOF
${freeze_output}
EOF
touch .venv-ndlocr/.install-complete
)
```

公式requirementsがPython 3.11で解決しない場合は、エラーを保存して保留にする。依存を無断で最新版へ置き換えたり、Node AのCUDAやOSを下げたりしない。Dockerへ切り替える場合は、公式提供物とライセンスを別途確認してから手順書を改訂する。

## 8. 全venvの導入確認

次の確認はパッケージを変更しない。

```bash
validation_failed=0
for venv_dir in .venv-anydoc .venv-docling .venv-mineru .venv-docling-vlm .venv-paddleocr .venv-olmocr .venv-marker .venv-yomitoku .venv-ndlocr; do if [ -x "${venv_dir}/bin/python" ] && [ -f "${venv_dir}/.install-complete" ]; then if ! "${venv_dir}/bin/python" -m pip check; then validation_failed=1; fi; else printf '%s\n' "保留または未完了: ${venv_dir}"; fi; done
du -sh .venv-* || true
df -h .
nvidia-smi
[ "${validation_failed}" -eq 0 ]
```

`pip check` の失敗を無視して変換へ進まない。保留したプロダクトは、理由を `results/comparison.md` に記録する。

## 9. モデル取得と初回動作確認

パッケージの一括導入とモデル取得を分ける。MinerUの明示取得を除き、多くのプロダクトは初回変換時にモデルを取得するためである。

1. [サンプル選定手順](../README.md#実行順序)で `sample_list.csv` を確定する。
2. 各[変換手順書](convert/)のサンプル変換を1プロダクトずつ実行する。
3. 初回のモデル取得が完了した後、同じ文書を `--force` で再実行して速度を測る。
4. `nvidia-smi` で別プロダクトのプロセスが残っていないことを確認してから次へ進む。

変換時も `source` は不要である。例えばDoclingは次のように実行できる。

```bash
.venv-docling/bin/python scripts/convert_docling.py
```

## 10. 再実行と障害の切り分け

- venvが正常なら同じインストールコマンドを再実行してよい。pipは導入済みの要件を再利用する。ただし、浮動要件は後日の再実行で版が変わる可能性がある。再実行前に `${product}` を対象識別子へ置き換え、`cp -v "metrics/${product}-versions.txt" "metrics/${product}-versions.before.txt"` で保存する。再実行後に `diff -u "metrics/${product}-versions.before.txt" "metrics/${product}-versions.txt"` で差分を確認する。
- 一つのvenvだけが壊れた場合は、原因を確認してからそのvenvだけを作り直す。他のvenvを削除しない。
- gp3の空き容量が不足した場合は、モデルを無断で削除しない。使用する上位プロダクトを選定してから、不要候補のvenvとキャッシュの削除対象を明示する。
- シェルを開き直してもvenvは残る。venv内のPythonを直接指定すれば、activate状態に依存せず再開できる。
