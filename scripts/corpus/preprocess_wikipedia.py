#!/usr/bin/env python3
"""WikiExtractor を実行し、Wikipedia 記事を記事単位のプレーンテキストへ分割する。"""

from __future__ import annotations

import argparse
import bz2
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
CATEGORY_PATTERN = re.compile(r"\[\[(?:Category|カテゴリ):([^\]|]+)", re.IGNORECASE)


def load_env() -> dict[str, str]:
    env_file = SCRIPT_DIR / "corpus.env"
    if not env_file.is_file():
        raise SystemExit(
            f"設定ファイルがありません: {env_file}\n"
            f"先に cp -v {SCRIPT_DIR / 'corpus.env.example'} {env_file} を実行してください。"
        )
    values: dict[str, str] = {}
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        parsed = shlex.split(raw_value, comments=True, posix=True)
        value = parsed[0] if parsed else ""
        values[key.strip()] = os.path.expandvars(os.path.expanduser(value))
    return values


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def open_dump(path: Path):
    return bz2.open(path, "rb") if path.suffix == ".bz2" else path.open("rb")


def page_value(page: ET.Element, name: str) -> str:
    element = next((item for item in page.iter() if local_name(item.tag) == name), None)
    return (element.text or "").strip() if element is not None else ""


def select_pages(input_path: Path, output_path: Path, categories: set[str], limit: int) -> int:
    selected = 0
    siteinfo_written = False
    namespace = "http://www.mediawiki.org/xml/export-0.11/"
    ET.register_namespace("", namespace)

    with open_dump(input_path) as source, output_path.open("wb") as target:
        target.write(b'<?xml version="1.0" encoding="utf-8"?>\n')
        target.write(f'<mediawiki xmlns="{namespace}" version="0.11" xml:lang="ja">\n'.encode())
        for _, element in ET.iterparse(source, events=("end",)):
            tag = local_name(element.tag)
            if tag == "siteinfo" and not siteinfo_written:
                target.write(ET.tostring(element, encoding="utf-8"))
                target.write(b"\n")
                siteinfo_written = True
                element.clear()
                continue
            if tag != "page":
                continue

            namespace_id = page_value(element, "ns")
            text = page_value(element, "text")
            page_categories = {item.strip() for item in CATEGORY_PATTERN.findall(text)}
            category_match = not categories or bool(categories & page_categories)
            if namespace_id == "0" and category_match:
                target.write(ET.tostring(element, encoding="utf-8"))
                target.write(b"\n")
                selected += 1
                if limit and selected >= limit:
                    element.clear()
                    break
            element.clear()
        target.write(b"</mediawiki>\n")
    return selected


def safe_filename(article_id: str, title: str) -> str:
    normalized = unicodedata.normalize("NFKC", title)
    normalized = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", normalized)
    normalized = re.sub(r"\s+", "_", normalized).strip("._")[:100] or "article"
    return f"{article_id}_{normalized}.txt"


def iter_json_records(extracted_dir: Path):
    for path in sorted(extracted_dir.rglob("*")):
        if not path.is_file():
            continue
        with path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(f"WikiExtractor JSON の解析に失敗: {path}:{line_number}") from exc


def parse_args(env: dict[str, str]) -> argparse.Namespace:
    corpus_dir = Path(env.get("CORPUS_DIR", "~/rag-corpus")).expanduser()
    default_input_dir = corpus_dir / "raw" / "wikipedia"
    dumps = sorted(default_input_dir.glob("*.bz2"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, default=dumps[0] if dumps else None)
    parser.add_argument("--output-dir", type=Path, default=corpus_dir / "processed" / "wikipedia")
    parser.add_argument("--max-articles", type=int, default=int(env.get("WIKIPEDIA_MAX_ARTICLES", "0")))
    parser.add_argument("--category", action="append", default=[])
    parser.add_argument("--processes", type=int, default=int(env.get("WIKIEXTRACTOR_PROCESSES", "4")))
    parser.add_argument("--expand-templates", action="store_true")
    args = parser.parse_args()
    env_categories = [item.strip() for item in env.get("WIKIPEDIA_CATEGORIES", "").split(",") if item.strip()]
    args.category = args.category or env_categories
    if args.input is None:
        parser.error(f"Wikipedia ダンプがありません: {default_input_dir}")
    if args.max_articles < 0:
        parser.error("--max-articles は 0 以上で指定してください")
    return args


def main() -> int:
    env = load_env()
    args = parse_args(env)
    input_path = args.input.resolve()
    if not input_path.is_file():
        raise SystemExit(f"Wikipedia ダンプがありません: {input_path}")
    if args.expand_templates and (args.category or args.max_articles):
        raise SystemExit("カテゴリ/件数で事前抽出する場合は --expand-templates を使用できません")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    categories = set(args.category)
    with tempfile.TemporaryDirectory(prefix="wikiextractor-") as temporary:
        temporary_dir = Path(temporary)
        extractor_input = input_path
        if categories or args.max_articles:
            extractor_input = temporary_dir / "selected-pages.xml"
            selected = select_pages(input_path, extractor_input, categories, args.max_articles)
            print(f"WikiExtractor 事前抽出: {selected} 記事")
            if selected == 0:
                raise SystemExit("指定条件に一致する Wikipedia 記事がありません")

        extracted_dir = temporary_dir / "json"
        command = [
            sys.executable,
            "-m",
            "wikiextractor.WikiExtractor",
            str(extractor_input),
            "--json",
            "--output",
            str(extracted_dir),
            "--bytes",
            "10M",
            "--processes",
            str(args.processes),
        ]
        if not args.expand_templates:
            command.append("--no-templates")
        print("WikiExtractor 実行: " + " ".join(command))
        subprocess.run(command, check=True)

        written = 0
        skipped = 0
        for record in iter_json_records(extracted_dir):
            article_id = str(record.get("id", "unknown"))
            title = str(record.get("title", "無題"))
            text = str(record.get("text", "")).strip()
            if not text:
                continue
            output_path = args.output_dir / safe_filename(article_id, title)
            if output_path.is_file():
                skipped += 1
                continue
            source_url = str(record.get("url", "")) or f"https://ja.wikipedia.org/?curid={article_id}"
            content = (
                f"タイトル: {title}\n"
                f"出典: {source_url}\n"
                "ライセンス: CC BY-SA 4.0\n\n"
                f"{text}\n"
            )
            output_path.write_text(content, encoding="utf-8", newline="\n")
            written += 1
            if written % 1000 == 0:
                print(f"プレーンテキスト出力: {written} 件")

    total = sum(1 for item in args.output_dir.glob("*.txt") if item.is_file())
    print(f"Wikipedia 前処理結果: 新規 {written} 件 / スキップ {skipped} 件 / 保存済み {total} 件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
