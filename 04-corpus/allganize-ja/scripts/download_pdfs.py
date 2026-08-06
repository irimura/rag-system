#!/usr/bin/env python3
"""RAG-Evaluation-Dataset-JA の公開元 PDF を一括取得する。"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


USER_AGENT = "rag-system-corpus-downloader/1.0 (+https://huggingface.co/datasets/allganize/RAG-Evaluation-Dataset-JA)"
MANIFEST_FIELDS = [
    "文書名",
    "URL",
    "成否",
    "HTTPステータス",
    "保存パス",
    "ファイルサイズ",
    "期待ページ数",
    "実ページ数",
    "ページ数一致",
    "エラー",
]


@dataclass
class DownloadResult:
    status: int | None
    content_type: str
    error: str = ""


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--dataset-dir", type=Path, default=root / "dataset", help="CSV を含む Hugging Face clone 先")
    parser.add_argument("--output-dir", type=Path, default=root / "pdfs", help="PDF 保存先")
    parser.add_argument("--manifest", type=Path, default=root / "manifest.csv", help="manifest.csv の保存先")
    parser.add_argument("--timeout", type=float, default=30.0, help="1 回の HTTP タイムアウト秒（既定: 30）")
    parser.add_argument("--interval", type=float, default=1.0, help="HTTP リクエスト開始間隔の秒数（既定: 1）")
    return parser.parse_args()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"ヘッダーがありません: {path}")
        return list(reader)


def normalized_name(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip())


def load_target_names(path: Path) -> dict[str, str]:
    rows = read_rows(path)
    if not rows or "target_file_name" not in rows[0]:
        raise ValueError(f"target_file_name 列がありません: {path}")
    targets: dict[str, str] = {}
    for row in rows:
        original = row["target_file_name"].strip()
        key = normalized_name(original)
        if not key:
            continue
        previous = targets.setdefault(key, original)
        if previous != original:
            raise ValueError(f"Unicode 正規化後に名前が衝突します: {previous!r}, {original!r}")
    return targets


def validate_filename(name: str) -> str:
    if not name or name in {".", ".."} or Path(name).name != name or "/" in name or "\\" in name:
        raise ValueError(f"安全でないファイル名です: {name!r}")
    if Path(name).suffix.lower() != ".pdf":
        raise ValueError(f"PDF ではないファイル名です: {name!r}")
    return name


class Downloader:
    def __init__(self, timeout: float, interval: float) -> None:
        self.timeout = timeout
        self.interval = interval
        self.last_request_started: float | None = None

    def _wait_for_interval(self) -> None:
        if self.last_request_started is None:
            return
        remaining = self.interval - (time.monotonic() - self.last_request_started)
        if remaining > 0:
            time.sleep(remaining)

    def fetch(self, url: str, destination: Path) -> DownloadResult:
        temporary = destination.with_name(f".{destination.name}.part")
        for attempt in range(1, 4):
            self._wait_for_interval()
            self.last_request_started = time.monotonic()
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/pdf"})
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    status = response.status
                    content_type = response.headers.get_content_type().lower()
                    body = response.read()
                if content_type == "text/html" or b"%PDF-" not in body[:1024]:
                    return DownloadResult(status, content_type, f"PDF 直リンクではありません (Content-Type: {content_type})")
                temporary.write_bytes(body)
                os.replace(temporary, destination)
                return DownloadResult(status, content_type)
            except urllib.error.HTTPError as exc:
                status = exc.code
                error = f"HTTP {status}: {exc.reason}"
                retryable = status == 429 or 500 <= status <= 599
                if not retryable or attempt == 3:
                    return DownloadResult(status, exc.headers.get_content_type().lower(), error)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                status = None
                error = f"{type(exc).__name__}: {exc}"
                if attempt == 3:
                    return DownloadResult(status, "", error)
            finally:
                temporary.unlink(missing_ok=True)
            delay = 2 ** (attempt - 1)
            print(f"  一時エラーのため {delay} 秒後に再試行します ({attempt}/3)", file=sys.stderr)
            time.sleep(delay)
        raise AssertionError("到達不能")


def pdf_page_count(path: Path) -> int:
    return len(PdfReader(str(path)).pages)


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise ValueError
    return number


def run(args: argparse.Namespace) -> int:
    dataset_dir = args.dataset_dir.resolve()
    output_dir = (args.output_dir or dataset_dir / "pdfs").resolve()
    manifest_path = (args.manifest or dataset_dir / "manifest.csv").resolve()
    documents_path = dataset_dir / "documents.csv"
    results_path = dataset_dir / "rag_evaluation_result.csv"

    if args.timeout <= 0 or args.interval < 0:
        raise ValueError("--timeout は正数、--interval は 0 以上で指定してください")
    documents = read_rows(documents_path)
    required = {"title", "page", "url", "file_name"}
    if not documents or not required.issubset(documents[0]):
        raise ValueError(f"documents.csv に必要な列がありません: {', '.join(sorted(required))}")
    targets = load_target_names(results_path)
    documents_by_name: dict[str, dict[str, str]] = {}
    for document in documents:
        key = normalized_name(document["file_name"])
        if key in documents_by_name:
            raise ValueError(f"documents.csv 内で file_name が重複しています: {document['file_name']!r}")
        documents_by_name[key] = document
    missing_documents = sorted(set(targets) - set(documents_by_name))
    if missing_documents:
        raise ValueError(f"評価対象が documents.csv にありません: {', '.join(missing_documents)}")
    excluded = [document for key, document in documents_by_name.items() if key not in targets]
    documents = [document for document in documents if normalized_name(document["file_name"]) in targets]
    for document in excluded:
        print(f"評価結果から未参照のため対象外: {document['file_name']} ({document['title']})")
    print(f"評価対象: {len(documents)} 文書")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    downloader = Downloader(args.timeout, args.interval)
    manifest_rows: list[dict[str, object]] = []

    for index, document in enumerate(documents, 1):
        title = document["title"].strip()
        url = document["url"].strip()
        source_name = document["file_name"].strip()
        row: dict[str, object] = {field: "" for field in MANIFEST_FIELDS}
        row.update({"文書名": title, "URL": url, "成否": "失敗"})
        try:
            target_name = targets[normalized_name(source_name)]
            target_name = validate_filename(target_name)
            destination = output_dir / target_name
            expected_pages = positive_int(document["page"].strip())
            row.update({"保存パス": str(destination), "期待ページ数": expected_pages})
            print(f"[{index}/{len(documents)}] {target_name}")

            if destination.is_file():
                result = DownloadResult(None, "", "")
                print("  既存ファイルをスキップ")
            else:
                result = downloader.fetch(url, destination)
            row["HTTPステータス"] = result.status if result.status is not None else ""
            if result.error:
                raise RuntimeError(result.error)

            size = destination.stat().st_size
            actual_pages = pdf_page_count(destination)
            matches = actual_pages == expected_pages
            row.update(
                {
                    "成否": "成功",
                    "ファイルサイズ": size,
                    "実ページ数": actual_pages,
                    "ページ数一致": "一致" if matches else "不一致",
                }
            )
            if not matches:
                print(f"  警告: ページ数が不一致です (記載 {expected_pages}, 実際 {actual_pages})", file=sys.stderr)
        except Exception as exc:  # 文書単位で失敗を記録し、残りを続行する
            row["エラー"] = str(exc)
            print(f"  失敗: {exc}", file=sys.stderr)
        manifest_rows.append(row)

    with manifest_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(manifest_rows)

    failures = [row for row in manifest_rows if row["成否"] == "失敗"]
    successes = len(manifest_rows) - len(failures)
    mismatches = [row for row in manifest_rows if row["ページ数一致"] == "不一致"]
    print(f"\n完了: 成功 {successes} 件 / 失敗 {len(failures)} 件 / ページ数不一致 {len(mismatches)} 件")
    print(f"manifest: {manifest_path}")
    if failures:
        print("\n手動入手が必要な文書:")
        for row in failures:
            print(f"- {row['文書名']} | {row['URL']} | {row['エラー']}")
    return 1 if failures else 0


def main() -> int:
    try:
        return run(parse_args())
    except (OSError, ValueError, csv.Error) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
