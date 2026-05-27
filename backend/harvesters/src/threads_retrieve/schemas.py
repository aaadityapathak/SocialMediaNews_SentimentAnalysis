from datetime import datetime, timezone
from elasticsearch import helpers


def make_document(post: dict, keyword: str) -> dict:
    """Map a scraped post to an Elasticsearch document"""
    return {
        "keyword": keyword,
        "username": post.get("username"),
        "user_verified": post.get("user_verified"),
        "text": post.get("text", "").replace("\n", " ").strip(),
        "like_count": post.get("like_count"),
        "reply_count": post.get("reply_count"),
        "published_on": post.get("published_on"),
        "url": post.get("url"),
        "post_id": post.get("id"),
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


def upload_to_elasticsearch(es_client, documents: list, index_name: str) -> int:
    """Bulk upload documents with deduplication via post_id"""
    actions = [
        {
            "_index": index_name,
            "_id": doc["post_id"],
            "_source": doc,
        }
        for doc in documents
        if doc.get("post_id") and doc.get("text")
    ]

    if not actions:
        return 0

    try:
        success, failed = helpers.bulk(es_client, actions, raise_on_error=False)
        return success
    except Exception as e:
        print(f"Connection Error: {e}")
        return 0
