#!/usr/bin/env python3
"""Allganize JA の評価対象から再現可能な層化サンプルを選ぶ。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


def norm(value: str) -> str:
    return unicodedata.normalize("NFC", (value or "").strip())


def first(row: dict[str, str], names: tuple[str, ...], default: str = "") -> str:
    for name in names:
        if norm(row.get(name, "")):
            return norm(row[name])
    return default


def text_kind(row: dict[str, str]) -> str:
    explicit = first(row, ("document_type", "pdf_type", "text_type", "ocr_type"))
    if explicit:
        return explicit
    return "未判定"


def stable_rank(seed: int, name: str) -> str:
    return hashlib.sha256(f"{seed}:{name}".encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", type=Path, default=Path(__file__).parents[1] / "dataset")
    parser.add_argument("--pdf-dir", type=Path, default=Path(__file__).parents[1] / "pdfs")
    parser.add_argument("--output", type=Path, default=Path(__file__).parents[1] / "sample_list.csv")
    parser.add_argument("--size", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20260806)
    parser.add_argument(
        "--domain",
        help="指定したdomainと完全一致する文書をすべて選ぶ（大文字小文字は区別しない）",
    )
    args = parser.parse_args()

    with (args.dataset_dir / "documents.csv").open(encoding="utf-8-sig", newline="") as f:
        documents = list(csv.DictReader(f))
    with (args.dataset_dir / "rag_evaluation_result.csv").open(encoding="utf-8-sig", newline="") as f:
        evaluations = list(csv.DictReader(f))

    docs: dict[str, dict[str, str]] = {}
    for row in documents:
        name = first(row, ("file_name", "target_file_name", "filename"))
        if name:
            docs[name] = row

    eval_by_doc: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in evaluations:
        name = first(row, ("target_file_name", "file_name", "filename"))
        if name:
            eval_by_doc[name].append(row)

    candidates = []
    for name, evals in eval_by_doc.items():
        row = docs.get(name, {})
        domain = first(row, ("domain", "category", "industry"), "未分類")
        kinds = sorted({first(e, ("type", "question_type", "answer_type"), "未分類") for e in evals})
        candidates.append({
            "file_name": name,
            "domain": domain,
            "document_type_guess": text_kind(row),
            "evaluation_types": "|".join(kinds),
            "target_page_nos": "|".join(sorted({first(e, ("target_page_no", "page_no")) for e in evals if first(e, ("target_page_no", "page_no"))}, key=lambda x: (0, int(x)) if x.isdigit() else (1, x))),
            "pdf_exists": str((args.pdf_dir / name).is_file()).lower(),
        })

    selected: list[dict[str, str]] = []
    if args.domain:
        requested_domain = norm(args.domain)
        selected = sorted(
            (item for item in candidates if item["domain"].casefold() == requested_domain.casefold()),
            key=lambda item: item["file_name"],
        )
        if not selected:
            available = ", ".join(sorted({item["domain"] for item in candidates}))
            parser.error(f"domain={requested_domain!r} に一致する文書がありません。候補: {available}")
    else:
        # 貪欲集合被覆: domain、文書タイプ、評価typeの未充足要素を最も多く埋める文書を選ぶ。
        covered: Counter[str] = Counter()
        while candidates and len(selected) < args.size:
            def score(item: dict[str, str]) -> tuple[int, int, str]:
                features = {f"domain:{item['domain']}", f"doc:{item['document_type_guess']}"}
                features |= {f"eval:{v}" for v in item["evaluation_types"].split("|")}
                gain = sum(1 for feature in features if covered[feature] == 0)
                rarity = sum(1 for feature in features if covered[feature] < 2)
                return (-gain, -rarity, stable_rank(args.seed, item["file_name"]))

            chosen = min(candidates, key=score)
            candidates.remove(chosen)
            selected.append(chosen)
            covered.update({f"domain:{chosen['domain']}", f"doc:{chosen['document_type_guess']}"})
            covered.update(f"eval:{v}" for v in chosen["evaluation_types"].split("|"))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = ["file_name", "domain", "document_type_guess", "evaluation_types", "target_page_nos", "pdf_exists"]
    with args.output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(selected)
    print(f"selected={len(selected)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
