#!/usr/bin/env python3
"""プロダクト別ラッパーで共用する変換・計測処理。"""

from __future__ import annotations

import argparse
import csv
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

PRODUCTS = {
    "docling": "docling {input} --pipeline standard --to md --output {work}",
    "docling-vlm": "docling {input} --pipeline vlm --vlm-model granite_docling --to md --output {work}",
    "mineru": "mineru -p {input} -o {work} -b pipeline",
    "paddleocr": "paddleocr pp_structurev3 -i {input} --device gpu --use_doc_orientation_classify True --use_doc_unwarping False --use_textline_orientation True --save_path {work}",
    "anydoc": "{python} -c 'import anydoc, pathlib, sys; pathlib.Path(sys.argv[2]).write_text(anydoc.to_markdown(sys.argv[1]), encoding=\"utf-8\")' {input} {output}",
    "yomitoku": "yomitoku {input} -f md -o {work}",
    "ndlocr": "python {root}/vendor/ndlocr_cli/src/ocr.py --sourceimg {input} --output {work}",
    "olmocr": "{python} -m olmocr.pipeline {work} --markdown --pdfs {input}",
    "marker": "marker_single {input} --output_dir {work} --output_format markdown --disable_multiprocessing",
}

FIELDS = ["file_name", "page_count", "elapsed_seconds", "pages_per_second", "output_characters", "success", "error", "peak_memory_mib", "gpu_used", "vram_peak_mib"]


def gpu_memory(pids: set[int]) -> float:
    if not pids:
        return 0.0
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        total = 0.0
        for line in result.stdout.splitlines():
            pid_text, memory_text = (part.strip() for part in line.split(",", 1))
            if int(pid_text) in pids:
                total += float(memory_text)
        return total
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 0.0


def find_markdown(work: Path, expected: Path) -> Path | None:
    if expected.is_file():
        return expected
    files = sorted(work.rglob("*.md"), key=lambda p: (p.name != expected.name, -p.stat().st_size))
    return files[0] if files else None


def load_inputs(root: Path, all_files: bool) -> list[Path]:
    if all_files:
        return sorted((root / "pdfs").glob("*.pdf"))
    sample = root / "sample_list.csv"
    if not sample.is_file():
        raise FileNotFoundError(f"{sample} がありません。select_sample.py を先に実行してください")
    with sample.open(encoding="utf-8-sig", newline="") as f:
        names = [row["file_name"] for row in csv.DictReader(f)]
    return [root / "pdfs" / name for name in names]


def main(product: str) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="pdfs/*.pdf の全件を処理する")
    parser.add_argument("--force", action="store_true", help="変換済みの出力を上書きする")
    parser.add_argument("--command", help="実験用コマンド。{input},{output},{work},{root},{python}を使用可")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out_dir, metrics_path = root / "out" / product, root / "metrics" / f"{product}.csv"
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, dict[str, str]] = {}
    if metrics_path.is_file():
        with metrics_path.open(encoding="utf-8", newline="") as f:
            existing = {row["file_name"]: row for row in csv.DictReader(f)}

    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise SystemExit("共通venvへ pypdf と psutil をインストールしてください") from exc

    rows = existing.copy()
    failures = 0
    for pdf in load_inputs(root, args.all):
        output = out_dir / f"{pdf.stem}.md"
        if output.is_file() and not args.force:
            print(f"skip: {pdf.name}")
            continue
        page_count, error = 0, ""
        try:
            page_count = len(PdfReader(str(pdf)).pages)
        except Exception as exc:  # 暗号化・破損もメトリクスへ残す
            error = f"page count: {type(exc).__name__}: {exc}"
        stop = threading.Event()
        vram_peak = [0.0]
        memory_peak = [0.0]
        process_holder: list[subprocess.Popen[str] | None] = [None]
        def watch_resources() -> None:
            import psutil
            while not stop.is_set():
                proc = process_holder[0]
                if proc is None:
                    stop.wait(0.05)
                    continue
                try:
                    parent = psutil.Process(proc.pid)
                    family = [parent, *parent.children(recursive=True)]
                    resource_pid = os.environ.get("CONVERT_RESOURCE_PID")
                    if resource_pid:
                        resource_parent = psutil.Process(int(resource_pid))
                        family.extend([resource_parent, *resource_parent.children(recursive=True)])
                    family = list({member.pid: member for member in family}.values())
                    memory_peak[0] = max(memory_peak[0], sum(p.memory_info().rss for p in family if p.is_running()) / 1024**2)
                    vram_peak[0] = max(vram_peak[0], gpu_memory({p.pid for p in family if p.is_running()}))
                except (ValueError, psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                stop.wait(0.5)
        watcher = threading.Thread(target=watch_resources, daemon=True)
        watcher.start()
        started = time.perf_counter()
        success = False
        try:
            if not pdf.is_file():
                raise FileNotFoundError(pdf)
            with tempfile.TemporaryDirectory(prefix=f"{product}-") as tmp:
                work = Path(tmp)
                template = args.command or os.environ.get("CONVERT_COMMAND") or PRODUCTS[product]
                values = {"input": shlex.quote(str(pdf)), "output": shlex.quote(str(output)), "work": shlex.quote(str(work)), "root": shlex.quote(str(root)), "python": shlex.quote(sys.executable)}
                command = template.format(**values)
                child_env = os.environ.copy()
                executable_dir = str(Path(sys.executable).parent)
                child_env["PATH"] = executable_dir + os.pathsep + child_env.get("PATH", "")
                proc = subprocess.Popen(command, shell=True, executable="/bin/bash", stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=child_env)
                process_holder[0] = proc
                try:
                    stdout, stderr = proc.communicate(timeout=int(os.environ.get("CONVERT_TIMEOUT", "7200")))
                except subprocess.TimeoutExpired:
                    proc.kill(); stdout, stderr = proc.communicate()
                    raise TimeoutError(f"変換がタイムアウトしました: {stderr[-1000:]}")
                if proc.returncode:
                    raise RuntimeError((stderr or stdout)[-2000:])
                produced = find_markdown(work, output)
                if produced is None:
                    raise RuntimeError("Markdown出力を検出できません")
                if produced != output:
                    shutil.copyfile(produced, output)
                success = output.stat().st_size > 0
                if not success:
                    raise RuntimeError("Markdown出力が空です")
        except Exception as exc:
            failures += 1
            error = "; ".join(filter(None, (error, f"{type(exc).__name__}: {exc}")))[:4000]
        finally:
            elapsed = time.perf_counter() - started
            stop.set(); watcher.join(timeout=2)
        pages_per_second = f"{page_count / elapsed:.4f}" if success and elapsed and page_count else ""
        rows[pdf.name] = dict(zip(FIELDS, [pdf.name, page_count, f"{elapsed:.3f}", pages_per_second, len(output.read_text(encoding="utf-8")) if success else 0, str(success).lower(), error, f"{memory_peak[0]:.1f}", str(vram_peak[0] > 0).lower(), f"{vram_peak[0]:.0f}"]))
        with metrics_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS); writer.writeheader(); writer.writerows(rows.values())
        print(f"{'ok' if success else 'failed'}: {pdf.name} ({elapsed:.2f}s)")
    return 1 if failures else 0
