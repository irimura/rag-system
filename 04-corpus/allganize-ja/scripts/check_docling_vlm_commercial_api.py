#!/usr/bin/env python3
"""機密値と応答本文を表示せず、OpenAI互換VLMの画像入力を確認する。"""

from __future__ import annotations

import base64
import json
import os
import struct
import urllib.error
import urllib.request
import zlib
from urllib.parse import urlsplit


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name}を設定してください。")
    return value


def test_png_data_url() -> str:
    """外部ファイルを使わず、32×32ピクセルの白いPNGを生成する。"""
    width = height = 32
    raw = b"".join(b"\x00" + b"\xff\xff\xff" * width for _ in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def main() -> int:
    api_url = required_env("DOCLING_VLLM_URL")
    model_name = required_env("DOCLING_VLLM_MODEL")
    api_key = required_env("DOCLING_VLLM_API_KEY")
    parsed_url = urlsplit(api_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
        raise SystemExit("DOCLING_VLLM_URLにはHTTPまたはHTTPSのURLを設定してください。")
    if parsed_url.username or parsed_url.password or parsed_url.query or parsed_url.fragment:
        raise SystemExit("DOCLING_VLLM_URLへ認証情報、クエリー、フラグメントを含めないでください。")

    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Return only OK."},
                    {"type": "image_url", "image_url": {"url": test_png_data_url()}},
                ],
            }
        ],
        "temperature": 0,
        "max_tokens": 8,
    }
    request = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.load(response)
        content = result["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"画像入力確認: FAILED (HTTP {exc.code})") from None
    except urllib.error.URLError:
        raise SystemExit("画像入力確認: FAILED (接続失敗)") from None
    except (ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError):
        raise SystemExit("画像入力確認: FAILED (応答形式不一致)") from None

    print("画像入力確認: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
