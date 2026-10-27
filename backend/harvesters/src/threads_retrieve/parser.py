"""Pure Threads payload parsing, independent of browser dependencies."""

import json
import re
from html.parser import HTMLParser
from urllib.parse import quote


def parse_thread(data):
    if not isinstance(data, dict) or not isinstance(data.get("post"), dict):
        return {}
    post = data["post"]
    user = post.get("user") if isinstance(post.get("user"), dict) else {}
    caption = (
        post.get("caption") if isinstance(post.get("caption"), dict) else {}
    )
    replies = data.get("view_replies_cta_string")
    if isinstance(replies, str):
        match = re.match(r"([\d,]+)\b", replies)
        replies = int(match.group(1).replace(",", "")) if match else None
    result = {
        "text": caption.get("text"),
        "published_on": post.get("taken_at"),
        "id": post.get("id"),
        "username": user.get("username"),
        "user_verified": user.get("is_verified"),
        "reply_count": replies,
        "like_count": post.get("like_count"),
        "images": [],
        "videos": list(
            dict.fromkeys(
                item["url"]
                for item in post.get("video_versions") or []
                if isinstance(item, dict) and item.get("url")
            )
        ),
    }
    for item in post.get("carousel_media") or []:
        if not isinstance(item, dict):
            continue
        candidates = (item.get("image_versions2") or {}).get("candidates") or []
        if candidates:
            candidate = candidates[min(1, len(candidates) - 1)]
            if isinstance(candidate, dict) and candidate.get("url"):
                result["images"].append(candidate["url"])
    if result["username"] and post.get("code"):
        result["url"] = (
            f"https://www.threads.net/@{quote(str(result['username']), safe='')}"
            f"/post/{quote(str(post['code']), safe='')}"
        )
    return result


class _JsonScripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.datasets = []
        self.parts = None

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("type") == "application/json":
            self.parts = []

    def handle_data(self, data):
        if self.parts is not None:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.parts is not None:
            self.datasets.append("".join(self.parts))
            self.parts = None


def parse_page(html: str) -> list[dict]:
    parser = _JsonScripts()
    parser.feed(html)
    posts = {}
    for payload in parser.datasets:
        if "thread_items" not in payload:
            continue
        try:
            pending = [json.loads(payload)]
        except (ValueError, RecursionError):
            continue
        while pending:
            item = pending.pop()
            if isinstance(item, dict):
                for key, value in item.items():
                    if key == "thread_items" and isinstance(value, list):
                        for raw in value:
                            try:
                                post = parse_thread(raw)
                            except (AttributeError, TypeError, ValueError):
                                continue
                            if post.get("id") and post.get("text"):
                                posts[str(post["id"])] = post
                    elif isinstance(value, (dict, list)):
                        pending.append(value)
            elif isinstance(item, list):
                pending.extend(item)
    return list(posts.values())
