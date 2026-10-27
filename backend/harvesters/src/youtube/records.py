"""Pure transformations to the queue's existing YouTube record contract."""


def video_record(video: dict) -> dict:
    return {key: value for key, value in video.items() if key != "comments"}


def comment_record(comment: dict, video: dict) -> dict:
    return {
        "comment_id": comment["comment_id"],
        "video_id": video["video_id"],
        "video_topic": video["topic"],
        "video_channel": video["channel"],
        "video_published": video["published"],
        "text": comment.get("textOriginal") or comment.get("textDisplay") or "",
        "author": comment.get("authorDisplayName", ""),
        "like_count": comment.get("likeCount", 0),
        "published_at": comment.get("publishedAt"),
        "updated_at": comment.get("updatedAt"),
    }


def reply_record(reply: dict, comment: dict, video: dict) -> dict:
    return {
        "reply_id": reply["reply_id"],
        "comment_id": comment["comment_id"],
        "video_id": video["video_id"],
        "video_topic": video["topic"],
        "video_channel": video["channel"],
        "text": reply.get("textOriginal") or reply.get("textDisplay") or "",
        "author": reply.get("authorDisplayName", ""),
        "like_count": reply.get("likeCount", 0),
        "published_at": reply.get("publishedAt"),
        "updated_at": reply.get("updatedAt"),
    }


def wrap_record(kind: str, record: dict) -> dict:
    return {"source": "youtube", "data": {"kind": kind, "record": record}}


def iter_records(video: dict):
    yield "video", video_record(video)
    for comment in video.get("comments", []):
        yield "comment", comment_record(comment, video)
        for reply in comment.get("replies", []):
            yield "reply", reply_record(reply, comment, video)
