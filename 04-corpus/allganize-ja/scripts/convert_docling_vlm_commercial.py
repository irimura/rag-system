#!/usr/bin/env python3
"""非公開VLMを利用するDocling変換を共通ラッパーから実行する。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from convert_common import main


def configure_resource_monitor() -> None:
    value = os.environ.get("DOCLING_VLLM_PID", "").strip()
    if not value:
        raise SystemExit("DOCLING_VLLM_PIDを設定してください。モデル名やAPIキーは設定値に含めません。")
    try:
        pid = int(value)
        Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        raise SystemExit(f"DOCLING_VLLM_PIDのプロセスを確認できません: PID {value}") from exc
    os.environ["CONVERT_RESOURCE_PID"] = str(pid)


if __name__ == "__main__":
    if not any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        configure_resource_monitor()
    raise SystemExit(main("docling-vlm-commercial"))
