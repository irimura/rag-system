# Allganize 日本語PDF変換検証 INDEX

Allganize RAG-Evaluation-Dataset-JA の評価対象PDFを、Node A（g6.xlarge、NVIDIA L4 24 GB、4 vCPU、RAM 16 GB、Ubuntu 24.04）上で構造化テキストへ変換する検証資材です。いきなり64件を処理せず、約10件のサンプル比較後に有望なプロダクトだけを全件実行します。

## 文書一覧

- [製品説明資料](docs/products.md)
- [全プロダクト一括インストール手順書](docs/install-all.md)
- [比較手順書](docs/compare.md)
- 変換手順書: [Docling](docs/convert/docling.md) / [Docling VLM](docs/convert/docling-vlm.md) / [MinerU](docs/convert/mineru.md) / [PaddleOCR](docs/convert/paddleocr.md) / [AnyDoc](docs/convert/anydoc.md) / [YomiToku](docs/convert/yomitoku.md) / [NDLOCR](docs/convert/ndlocr.md) / [olmOCR](docs/convert/olmocr.md) / [Marker](docs/convert/marker.md)
- [比較結果](results/comparison.md)
- 点検結果: [products](checks/products.md) / [install-all](checks/install-all.md) / [compare](checks/compare.md) / [convert](checks/convert/)

## 実行順序

1. `dataset/` に `documents.csv` と `rag_evaluation_result.csv`、`pdfs/` に評価対象64件を配置します。
2. `python3 scripts/select_sample.py` を実行し、`sample_list.csv` を生成します。`document_type_guess` はメタデータから得た推定値にすぎません。「未判定」だけでなく全行のPDFを確認し、「文字埋込み」か「スキャン」に直します。
3. [製品説明資料](docs/products.md)でライセンスと適用範囲を確認します。
4. [一括インストール手順書](docs/install-all.md)に従い、各プロダクトを別venvへ導入します。
5. 各変換手順書に従い、サンプルだけを変換します。
6. [比較手順書](docs/compare.md)に従って速度、成功率、精度、表の再現性を評価します。
7. 選定基準を満たした上位プロダクトだけを `--all` 付きで再実行します。

`sample_list.csv` はデータ未配置のため、現在はヘッダーだけです。変換結果とメトリクスは大容量になるためGit管理しません。
