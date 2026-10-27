"""Threads document normalization and bounded Elasticsearch writes."""

from datetime import UTC, datetime

from elasticsearch import helpers


def make_document(post: dict, keyword: str) -> dict:
    return {
        "keyword": keyword,
        "username": post.get("username"),
        "user_verified": post.get("user_verified"),
        "text": str(post.get("text") or "").replace("\n", " ").strip(),
        "like_count": post.get("like_count"),
        "reply_count": post.get("reply_count"),
        "published_on": post.get("published_on"),
        "url": post.get("url"),
        "post_id": post.get("id"),
        "scraped_at": datetime.now(UTC).isoformat(),
    }


def upload_to_elasticsearch(es_client, documents, index_name: str) -> int:
    actions = (
        {"_index": index_name, "_id": doc["post_id"], "_source": doc}
        for doc in documents
        if doc.get("post_id") and doc.get("text")
    )
    success = failures = 0
    for ok, _ in helpers.streaming_bulk(
        es_client,
        actions,
        chunk_size=500,
        max_retries=3,
        initial_backoff=1,
        max_backoff=8,
        raise_on_error=False,
    ):
        if ok:
            success += 1
        else:
            failures += 1
    if failures:
        raise RuntimeError(f"Threads indexing failed for {failures} documents")
    return success
