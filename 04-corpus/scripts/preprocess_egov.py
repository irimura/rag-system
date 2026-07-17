#!/usr/bin/env python3
"""e-Gov 法令 XML を条・項構造を保った Markdown へ変換する。"""

from __future__ import annotations

import argparse
import os
import shlex
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


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


def clean_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return "".join(element.itertext()).replace("\u3000", " ").strip()


def child(element: ET.Element, name: str) -> ET.Element | None:
    return next((item for item in element if local_name(item.tag) == name), None)


def first_descendant(element: ET.Element, name: str) -> ET.Element | None:
    return next((item for item in element.iter() if local_name(item.tag) == name), None)


STRUCTURE_HEADINGS = {
    "Part": 2,
    "Chapter": 2,
    "Section": 3,
    "Subsection": 4,
    "Division": 5,
}


def render_item(element: ET.Element, depth: int = 0) -> list[str]:
    tag = local_name(element.tag)
    title = clean_text(child(element, f"{tag}Title"))
    sentence = clean_text(child(element, f"{tag}Sentence"))
    text = " ".join(part for part in (title, sentence) if part)
    lines = [f"{'  ' * depth}- {text}"] if text else []
    for nested in element:
        nested_tag = local_name(nested.tag)
        if nested_tag.startswith("Subitem") or nested_tag == "Item":
            lines.extend(render_item(nested, depth + 1))
    return lines


def render_container(element: ET.Element, lines: list[str]) -> None:
    tag = local_name(element.tag)

    if tag in STRUCTURE_HEADINGS:
        title = clean_text(child(element, f"{tag}Title"))
        if title:
            lines.extend([f"{'#' * STRUCTURE_HEADINGS[tag]} {title}", ""])
        for nested in element:
            if local_name(nested.tag) != f"{tag}Title":
                render_container(nested, lines)
        return

    if tag == "Article":
        title = clean_text(child(element, "ArticleTitle"))
        caption = clean_text(child(element, "ArticleCaption"))
        heading = "".join(part for part in (title, caption) if part)
        if heading:
            lines.extend([f"### {heading}", ""])
        for nested in element:
            if local_name(nested.tag) not in {"ArticleTitle", "ArticleCaption"}:
                render_container(nested, lines)
        return

    if tag == "Paragraph":
        number = clean_text(child(element, "ParagraphNum"))
        sentence = clean_text(child(element, "ParagraphSentence"))
        if sentence:
            prefix = f"{number} " if number else ""
            lines.extend([f"{prefix}{sentence}", ""])
        for nested in element:
            nested_tag = local_name(nested.tag)
            if nested_tag == "Item" or nested_tag.startswith("Subitem"):
                lines.extend(render_item(nested))
        if lines and lines[-1] != "":
            lines.append("")
        return

    if tag == "SupplProvision":
        label = clean_text(child(element, "SupplProvisionLabel")) or "附則"
        lines.extend([f"## {label}", ""])
        for nested in element:
            if local_name(nested.tag) != "SupplProvisionLabel":
                render_container(nested, lines)
        return

    if tag.startswith("Appdx"):
        title = clean_text(child(element, f"{tag}Title")) or tag
        lines.extend([f"## {title}", ""])
        body = clean_text(element)
        if body and body != title:
            lines.extend([body, ""])
        return

    for nested in element:
        render_container(nested, lines)


def convert(xml_path: Path, output_path: Path) -> None:
    root = ET.parse(xml_path).getroot()
    law = first_descendant(root, "Law") or root
    title = clean_text(first_descendant(law, "LawTitle")) or xml_path.stem
    law_num = clean_text(first_descendant(law, "LawNum"))
    law_id = xml_path.stem
    body = first_descendant(law, "LawBody") or law

    lines = [
        f"# {title}",
        "",
        f"- 法令番号: {law_num or '不明'}",
        f"- 法令 ID: {law_id}",
        f"- 出典: https://laws.e-gov.go.jp/law/{law_id}",
        "- 利用条件: 法令は著作権法第13条により著作権の目的とならない",
        "",
    ]
    render_container(body, lines)
    normalized = "\n".join(lines).rstrip() + "\n"
    output_path.write_text(normalized, encoding="utf-8", newline="\n")


def parse_args(env: dict[str, str]) -> argparse.Namespace:
    corpus_dir = Path(env.get("CORPUS_DIR", "~/rag-corpus")).expanduser()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=corpus_dir / "raw" / "egov")
    parser.add_argument("--output-dir", type=Path, default=corpus_dir / "processed" / "laws")
    return parser.parse_args()


def main() -> int:
    env = load_env()
    args = parse_args(env)
    inputs = sorted(args.input_dir.glob("*.xml"))
    if not inputs:
        raise SystemExit(f"法令 XML がありません: {args.input_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    converted = 0
    skipped = 0
    for xml_path in inputs:
        output_path = args.output_dir / f"{xml_path.stem}.md"
        if output_path.is_file() and output_path.stat().st_mtime >= xml_path.stat().st_mtime:
            print(f"前処理済みのためスキップ: {output_path}")
            skipped += 1
            continue
        convert(xml_path, output_path)
        print(f"変換完了: {xml_path} -> {output_path}")
        converted += 1

    print(f"e-Gov 前処理結果: 変換 {converted} 件 / スキップ {skipped} 件 / 合計 {len(inputs)} 件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
