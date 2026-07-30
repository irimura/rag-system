import os
import random

try:
    OWUI_API_KEY = os.environ["OWUI_API_KEY"]
except KeyError:
    raise SystemExit("環境変数 OWUI_API_KEY を設定してください。") from None

try:
    OWUI_MODEL = os.environ["OWUI_MODEL"]
except KeyError:
    raise SystemExit("環境変数 OWUI_MODEL を設定してください。") from None

import urllib3
from locust import HttpUser, between, task
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
                "stream": False,
            },
            name="/api/chat/completions",
            catch_response=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(
                    f"HTTP {response.status_code}: {response.text[:200]}"
                )
                return

            try:
                content = response.json()["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError, ValueError):
                response.failure("応答 JSON に choices[0].message.content がありません。")
                return

            if not isinstance(content, str) or not content.strip():
                response.failure("応答 JSON の choices[0].message.content が空です。")
