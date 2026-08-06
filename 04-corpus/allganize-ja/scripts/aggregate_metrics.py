#!/usr/bin/env python3
"""プロダクト別メトリクスを集約し、Markdown表を生成する。"""
from __future__ import annotations
import argparse, csv, statistics
from pathlib import Path

def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("--metrics-dir", type=Path); p.add_argument("--output", type=Path)
    a = p.parse_args(); root = Path(__file__).resolve().parents[1]
    metrics_dir = a.metrics_dir or root / "metrics"; output = a.output or root / "results" / "comparison.md"
    lines = ["# PDF変換比較結果", "", "> 実測値を集約した結果です。精度欄と選定判断は `docs/compare.md` に従って追記してください。", "", "| プロダクト | 成功/総数 | 成功率 | 中央値 秒/ページ | 合計文字数 | 最大ピークRAM MiB | 最大VRAM MiB | 精度評価 | 選定 |", "|---|---:|---:|---:|---:|---:|---:|---|---|"]
    for path in sorted(metrics_dir.glob("*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as f: rows = list(csv.DictReader(f))
        ok = [r for r in rows if r.get("success", "").lower() == "true"]
        spp = [float(r["elapsed_seconds"]) / float(r["page_count"]) for r in ok if float(r.get("page_count") or 0)]
        lines.append(f"| {path.stem} | {len(ok)}/{len(rows)} | {(100*len(ok)/len(rows) if rows else 0):.1f}% | {statistics.median(spp) if spp else 0:.3f} | {sum(int(r.get('output_characters') or 0) for r in ok)} | {max([float(r.get('peak_memory_mib') or 0) for r in rows] or [0]):.1f} | {max([float(r.get('vram_peak_mib') or 0) for r in rows] or [0]):.0f} | 未評価 | 未選定 |")
    output.parent.mkdir(parents=True, exist_ok=True); output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(output); return 0
if __name__ == "__main__": raise SystemExit(main())
