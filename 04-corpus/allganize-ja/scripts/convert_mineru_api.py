#!/usr/bin/env python3
"""常駐MinerU APIを利用して、PDF単位の変換とメトリクス記録を行う。"""

from __future__ import annotations

import os
import shlex
import sys
import urllib.error
import urllib.request
from pathlib import Path

from convert_common import main


def api_url() -> str:
    return os.environ.get("MINERU_API_URL", "http://127.0.0.1:8000").rstrip("/")


def check_api(url: str) -> None:
    try:
        with urllib.request.urlopen(f"{url}/openapi.json", timeout=5) as response:
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}")
    except (OSError, RuntimeError, urllib.error.URLError) as exc:
        raise SystemExit(
            f"MinerU APIへ接続できません: {url} ({exc})\n"
            "先に .venv-mineru/bin/mineru-api を起動してください。"
        ) from exc


def configure_resource_monitor() -> None:
    pid_file = Path(os.environ.get("MINERU_API_PID_FILE", "/tmp/allganize-mineru-api.pid"))
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
        command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
    except (OSError, ValueError) as exc:
        raise SystemExit(f"MinerU APIのPIDを確認できません: {pid_file} ({exc})") from exc
    if "mineru-api" not in command:
        raise SystemExit(f"PID {pid} はmineru-apiではありません: {command}")
    os.environ["CONVERT_RESOURCE_PID"] = str(pid)


if __name__ == "__main__":
    url = api_url()
    if not any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        check_api(url)
        configure_resource_monitor()
    os.environ.setdefault(
        "CONVERT_COMMAND",
        f"mineru -p {{input}} -o {{work}} -b pipeline --api-url {shlex.quote(url)}",
    )
    raise SystemExit(main("mineru"))
