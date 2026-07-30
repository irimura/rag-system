import json
import os
import random
import time

try:
    OWUI_API_KEY = os.environ["OWUI_API_KEY"]
except KeyError:
    raise SystemExit("環境変数 OWUI_API_KEY を設定してください。") from None

try:
    OWUI_MODEL = os.environ["OWUI_MODEL"]
except KeyError:
    raise SystemExit("環境変数 OWUI_MODEL を設定してください。") from None

import urllib3
from locust import HttpUser, between, events, task
from urllib3.exceptions import InsecureRequestWarning


QUESTIONS = [
    "登録されている文書の概要を説明してください。",
    "主要な要点を三つに整理してください。",
    "文書に記載された重要な注意事項を教えてください。",
    "関連する手順を順番に説明してください。",
    "文書の内容に基づいて、推奨事項をまとめてください。",
]

urllib3.disable_warnings(InsecureRequestWarning)


class OpenWebUiUser(HttpUser):
    # 実利用者が次の質問を入力するまでの思考時間を模擬する。
    wait_time = between(1, 3)

    def on_start(self):
        self.client.verify = False

    @task
    def chat_completion(self):
        started = time.perf_counter()
        with self.client.post(
            "/api/chat/completions",
            headers={"Authorization": f"Bearer {OWUI_API_KEY}"},
            json={
                "model": OWUI_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": random.choice(QUESTIONS),
                    }
                ],
                "stream": True,
            },
            name="/api/chat/completions",
            stream=True,
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(
                    f"HTTP {response.status_code}: {response.text[:200]}"
                )
                return

            first_content_at = None
            content_chunks = []
            done_received = False
            for line in response.iter_lines():
                if not line or not line.startswith(b"data: "):
                    continue
                data = line[6:].decode("utf-8", errors="replace")
                if data == "[DONE]":
                    done_received = True
                    break
                try:
                    content = json.loads(data)["choices"][0]["delta"]["content"]
                except (KeyError, IndexError, TypeError, ValueError):
                    # [DONE] 以外でも解析できない SSE 行は測定対象外とする。
                    continue
                if not isinstance(content, str) or not content:
                    continue
                if first_content_at is None:
                    first_content_at = time.perf_counter()
                content_chunks.append(content)

            finished = time.perf_counter()
            total_seconds = finished - started
            response.request_meta["response_time"] = total_seconds * 1000

            if not done_received:
                response.failure("data: [DONE] を受信できませんでした。")
                return
            if not content_chunks:
                response.failure("コンテンツチャンクがありません。")
                return
            if not "".join(content_chunks).strip():
                response.failure("連結した応答テキストが空です。")
                return

            ttft_seconds = first_content_at - started
            # トークン数はコンテンツチャンク数で近似する。
            chunk_count = len(content_chunks)
            tpot_seconds = (
                (total_seconds - ttft_seconds) / max(chunk_count - 1, 1)
            )
            tokens_per_s = chunk_count / total_seconds
            events.request.fire(
                request_type="SSE",
                name="ttft",
                response_time=ttft_seconds * 1000,
                response_length=0,
                exception=None,
            )
            events.request.fire(
                request_type="SSE",
                name="tpot",
                response_time=tpot_seconds * 1000,
                response_length=0,
                exception=None,
            )
            # response_time 欄を流用するが、この値の単位は ms ではなく tokens/s。
            events.request.fire(
                request_type="SSE",
                name="tokens_per_s",
                response_time=tokens_per_s,
                response_length=0,
                exception=None,
            )
