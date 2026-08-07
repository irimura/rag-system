#!/usr/bin/env python3
"""OpenAI互換の非公開VLMを使い、PDFをMarkdownへ変換する。"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from urllib.parse import urlsplit


DEFAULT_PROMPT = """Convert this document page to complete Markdown.
Preserve headings, paragraphs, lists, tables, formulas, captions, and reading order.
Do not summarize, omit, or invent content. Return only Markdown."""


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name}を設定してください。")
    return value


def integer_env(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        raise SystemExit(f"{name}には整数を設定してください。") from None
    if value < 1:
        raise SystemExit(f"{name}は1以上にしてください。")
    return value


def positive_float_env(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except ValueError:
        raise SystemExit(f"{name}には数値を設定してください。") from None
    if value <= 0:
        raise SystemExit(f"{name}は0より大きくしてください。")
    return value


def load_prompt() -> str:
    prompt_file = os.environ.get("DOCLING_VLLM_PROMPT_FILE", "").strip()
    if not prompt_file:
        return DEFAULT_PROMPT
    prompt = Path(prompt_file).read_text(encoding="utf-8").strip()
    if not prompt:
        raise SystemExit("DOCLING_VLLM_PROMPT_FILEの内容が空です。")
    return prompt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    api_url = required_env("DOCLING_VLLM_URL")
    model_name = required_env("DOCLING_VLLM_MODEL")
    api_key = required_env("DOCLING_VLLM_API_KEY")
    parsed_url = urlsplit(api_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
        raise SystemExit("DOCLING_VLLM_URLにはHTTPまたはHTTPSのURLを設定してください。")
    if parsed_url.username or parsed_url.password or parsed_url.query or parsed_url.fragment:
        raise SystemExit("DOCLING_VLLM_URLへ認証情報、クエリー、フラグメントを含めないでください。")

    try:
        logging.disable(logging.CRITICAL)
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import VlmPipelineOptions
        from docling.datamodel.pipeline_options_vlm_model import ApiVlmOptions, ResponseFormat
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.pipeline.vlm_pipeline import VlmPipeline

        pipeline_options = VlmPipelineOptions(enable_remote_services=True)
        pipeline_options.vlm_options = ApiVlmOptions(
            url=api_url,
            headers={"Authorization": f"Bearer {api_key}"},
            params={
                "model": model_name,
                "max_tokens": integer_env("DOCLING_VLLM_MAX_TOKENS", 8192),
                "skip_special_tokens": False,
            },
            prompt=load_prompt(),
            concurrency=integer_env("DOCLING_VLLM_CONCURRENCY", 4),
            timeout=integer_env("DOCLING_VLLM_TIMEOUT", 300),
            scale=positive_float_env("DOCLING_VLLM_SCALE", 2.0),
            temperature=0.0,
            response_format=ResponseFormat.MARKDOWN,
        )
        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_cls=VlmPipeline,
                    pipeline_options=pipeline_options,
                )
            }
        )
        document = converter.convert(args.input).document
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(document.export_to_markdown(), encoding="utf-8")
    except Exception as exc:
        message = str(exc).replace(model_name, "[REDACTED_MODEL]").replace(api_key, "[REDACTED_API_KEY]")
        raise SystemExit(f"{type(exc).__name__}: {message}") from None
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
