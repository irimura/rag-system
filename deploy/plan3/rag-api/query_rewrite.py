"""再検索クエリ生成のプロンプト組み立て。"""

REWRITE_PROMPT = """文書検索の結果が不十分でした。別の観点の検索クエリを 1 つだけ出力してください。
元の質問の同義語・正式名称・上位/下位概念を使い、直前の検索クエリとは異なる語句にしてください。
説明は不要です。

試行回数: {attempt}
元の質問: {question}
検索済みクエリ(再利用禁止):
{query_history}"""


def build_rewrite_prompt(question: str, previous_queries: list[str], attempt: int) -> str:
    if attempt < 1:
        raise ValueError("attempt は 1 以上である必要があります")
    return REWRITE_PROMPT.format(
        question=question,
        query_history="\n".join(f"- {query}" for query in previous_queries),
        attempt=attempt,
    )