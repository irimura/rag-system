import os
from pathlib import Path


target = Path(
    os.environ.get(
        "OPEN_WEBUI_UTILS_PATH",
        "/app/backend/open_webui/retrieval/utils.py",
    )
)
source = target.read_text(encoding="utf-8")


def replace_once(old: str, new: str) -> None:
    global source
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one patch target, found {count}: {old[:80]!r}")
    source = source.replace(old, new, 1)


replace_once(
    "from urllib.parse import quote\n",
    "from urllib.parse import quote\nfrom uuid import uuid4\n",
)

replace_once(
    """        # Sentence transformers: CPU-bound sync operation
        async def async_embedding_function(query, prefix=None, user=None):
            return await asyncio.to_thread(
                (
                    lambda query, prefix=None: embedding_function.encode(
                        query,
                        batch_size=int(embedding_batch_size),
                        **({'prompt': prefix} if prefix else {}),
                    ).tolist()
                ),
                query,
                prefix,
            )
""",
    """        # Sentence transformers: CPU-bound sync operation
        async def async_embedding_function(query, prefix=None, user=None):
            batch_id = f'emb-{uuid4().hex[:12]}'
            item_count = len(query) if isinstance(query, list) else 1
            configured_batch_size = int(embedding_batch_size)
            batch_count = (item_count + configured_batch_size - 1) // configured_batch_size
            started_at = time.perf_counter()
            log.info(
                'RAG_BATCH_START id=%s type=embedding items=%d batch_size=%d batches=%d',
                batch_id,
                item_count,
                configured_batch_size,
                batch_count,
            )
            try:
                result = await asyncio.to_thread(
                    (
                        lambda query, prefix=None: embedding_function.encode(
                            query,
                            batch_size=configured_batch_size,
                            show_progress_bar=False,
                            **({'prompt': prefix} if prefix else {}),
                        ).tolist()
                    ),
                    query,
                    prefix,
                )
            except Exception:
                log.exception(
                    'RAG_BATCH_END id=%s type=embedding status=error elapsed_ms=%.1f',
                    batch_id,
                    (time.perf_counter() - started_at) * 1000,
                )
                raise
            log.info(
                'RAG_BATCH_END id=%s type=embedding status=success elapsed_ms=%.1f',
                batch_id,
                (time.perf_counter() - started_at) * 1000,
            )
            return result
""",
)

replace_once(
    """    else:
        return lambda query, documents, user=None: reranking_function.predict(
            [(query, doc.page_content) for doc in documents], batch_size=int(reranking_batch_size)
        )
""",
    """    else:
        def rerank(query, documents, user=None):
            batch_id = f'rerank-{uuid4().hex[:12]}'
            pairs = [(query, doc.page_content) for doc in documents]
            configured_batch_size = int(reranking_batch_size)
            batch_count = (len(pairs) + configured_batch_size - 1) // configured_batch_size
            started_at = time.perf_counter()
            log.info(
                'RAG_BATCH_START id=%s type=rerank items=%d batch_size=%d batches=%d',
                batch_id,
                len(pairs),
                configured_batch_size,
                batch_count,
            )
            try:
                result = reranking_function.predict(
                    pairs,
                    batch_size=configured_batch_size,
                    show_progress_bar=False,
                )
            except Exception:
                log.exception(
                    'RAG_BATCH_END id=%s type=rerank status=error elapsed_ms=%.1f',
                    batch_id,
                    (time.perf_counter() - started_at) * 1000,
                )
                raise
            log.info(
                'RAG_BATCH_END id=%s type=rerank status=success elapsed_ms=%.1f',
                batch_id,
                (time.perf_counter() - started_at) * 1000,
            )
            return result

        return rerank
""",
)

target.write_text(source, encoding="utf-8")
