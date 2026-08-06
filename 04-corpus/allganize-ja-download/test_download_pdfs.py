import csv
import importlib.util
import io
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfWriter


SCRIPT = Path(__file__).with_name("download_pdfs.py")
SPEC = importlib.util.spec_from_file_location("download_pdfs", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
download_pdfs = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = download_pdfs
SPEC.loader.exec_module(download_pdfs)


class FakeHeaders:
    def __init__(self, content_type: str) -> None:
        self.content_type = content_type

    def get_content_type(self) -> str:
        return self.content_type


class FakeResponse:
    def __init__(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.body = body
        self.headers = FakeHeaders(content_type)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def make_pdf(page_count: int) -> bytes:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=100, height=100)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


class DownloadPdfsTest(unittest.TestCase):
    def test_transient_error_retries_three_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "retry.pdf"
            downloader = download_pdfs.Downloader(timeout=1, interval=0)
            responses = [urllib.error.URLError("temporary"), urllib.error.URLError("temporary"), FakeResponse(make_pdf(1), "application/pdf")]
            with patch.object(download_pdfs.urllib.request, "urlopen", side_effect=responses) as mocked:
                with patch.object(download_pdfs.time, "sleep") as sleep:
                    result = downloader.fetch("https://example.test/retry", destination)
            self.assertEqual(result.error, "")
            self.assertEqual(mocked.call_count, 3)
            self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2])

    def test_download_manifest_page_check_and_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            dataset = Path(temporary)
            with (dataset / "documents.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["domain", "title", "page", "url", "file_name", "publisher"])
                writer.writeheader()
                writer.writerow({"title": "成功文書", "page": "1", "url": "https://example.test/good", "file_name": "good.pdf"})
                writer.writerow({"title": "HTML文書", "page": "1", "url": "https://example.test/html", "file_name": "html.pdf"})
                writer.writerow({"title": "評価対象外", "page": "1", "url": "https://example.test/extra", "file_name": "extra.pdf"})
            with (dataset / "rag_evaluation_result.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["target_file_name"])
                writer.writeheader()
                writer.writerows([{"target_file_name": "good.pdf"}, {"target_file_name": "html.pdf"}])

            responses = [FakeResponse(make_pdf(1), "application/pdf"), FakeResponse(b"<html></html>", "text/html")]
            args = download_pdfs.argparse.Namespace(dataset_dir=dataset, output_dir=None, manifest=None, timeout=1, interval=0)
            with patch.object(download_pdfs.urllib.request, "urlopen", side_effect=responses):
                self.assertEqual(download_pdfs.run(args), 1)

            rows = download_pdfs.read_rows(dataset / "manifest.csv")
            self.assertEqual([row["成否"] for row in rows], ["成功", "失敗"])
            self.assertEqual(rows[0]["実ページ数"], "1")
            self.assertIn("PDF 直リンクではありません", rows[1]["エラー"])

            with patch.object(download_pdfs.urllib.request, "urlopen", return_value=FakeResponse(make_pdf(1), "application/pdf")) as mocked:
                self.assertEqual(download_pdfs.run(args), 0)
                self.assertEqual(mocked.call_count, 1)  # good.pdf は既存のためスキップ


if __name__ == "__main__":
    unittest.main()
