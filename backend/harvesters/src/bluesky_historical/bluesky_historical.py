import asyncio
import logging
import re
import json
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any

import fire
import httpx
from valkey.asyncio import Valkey
from elasticsearch import AsyncElasticsearch
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from base import setup_logging
from elastic import ESSettings

setup_logging()
logger = logging.getLogger(__name__)


DEFAULT_AU_SEARCH_QUERIES = [
    "auspol",
    "ausvotes",
    "australian government",
    "australia voting",
    "australian elections",
    "australia politics",
    "australian federal election",
    "election day australia",
    "labor party australia",
    "liberal party australia",
    "australian greens",
    "the nationals australia",
    "one nation australia",
    "teal independent",
    "anthony albanese",
    "peter dutton",
    "adam bandt",
    "jim chalmers",
    "sussan ley",
    "cost of living australia",
    "housing australia",
]

STRONG_AU_KEYWORDS = [
    "australia",
    "australian",
    "aussie",
    "aussies",
    "auspol",
    "ausvotes",
    "ausvotes25",
    "ausvotes2025",
    "new south wales",
    "queensland",
    "south australia",
    "western australia",
    "tasmania",
    "northern territory",
    "abc australia",
    "sbs australia",
    "guardian australia",
    "the australian",
    "straya",
    "labor party",
    "labour party",
    "liberal party",
    "australian greens",
    "the nationals",
    "federal election",
    "australian federal election",
    "election day",
    "polling booth",
    "preferential voting",
    "senate australia",
]

MEDIUM_AU_KEYWORDS = [
    "victoria state",
    "state of victoria",
    "victorian government",
    "victorian parliament",
    "nsw government",
    "nsw parliament",
    "qld government",
    "queensland government",
    "nswpol",
    "vicpol",
    "qldpol",
    "melbourne vic",
    "melbourne victoria",
    "sydney nsw",
    "brisbane qld",
    "canberra act",
    "adelaide sa",
    "perth wa",
    "hobart tas",
    "darwin nt",
    "gold coast qld",
    "gold coast queensland",
    "geelong vic",
    "geelong victoria",
    "cairns queensland",
    "wollongong nsw",
    "teals",
    "teal independent",
    "pauline hanson",
    "peter dutton",
    "adam bandt",
    "penny wong",
    "jim chalmers",
    "tanya plibersek",
    "sussan ley",
    "david littleproud",
    "jacqui lambie",
    "andrew wilkie",
    "david pocock",
    "cost of living",
    "housing crisis",
    "abc news",
    "sky news australia",
    "news.com.au",
    "marginal seat",
    "two party preferred",
    "primary vote",
]

WEAK_CITY_KEYWORDS = [
    "victoria",
    "melbourne",
    "sydney",
    "canberra",
    "adelaide",
    "brisbane",
    "perth",
    "hobart",
    "darwin",
    "geelong",
    "gold coast",
    "sunshine coast",
    "newcastle",
    "wollongong",
    "ballarat",
    "bendigo",
    "toowoomba",
    "townsville",
    "cairns",
    "launceston",
    "alp",
    "nlp",
    "one nation",
    "greens",
    "senate",
    "parliament",
    "electorate",
    "albo",
    "dutton",
    "bandt",
]


class BlueskyHistoricalSettings(BaseSettings):
    base_url: str = Field(default="https://bsky.social")
    create_session_endpoint: str = Field(
        default="/xrpc/com.atproto.server.createSession"
    )
    search_endpoint: str = Field(default="/xrpc/app.bsky.feed.searchPosts")

    handle: str = Field(description="Bluesky handle / identifier")
    app_password: str = Field(description="Bluesky app password")

    user_agent: str = Field(default="unimelb-comp90024-t23-historical")
    timeout_seconds: float = Field(default=30.0, gt=0)

    index_name: str = Field(default="bluesky-historical-idx")
    page_size: int = Field(default=100, ge=1, le=100)
    max_pages: int = Field(default=5, ge=1)

    # Melbourne 2026-05-10 00:00 = UTC 2026-05-09T14:00:00Z
    cutoff_before: str = Field(default="2026-05-09T14:00:00Z")
    split_by_3day: bool = Field(default=True)

    model_config = SettingsConfigDict(env_prefix="BLUESKY_")

    max_retries: int = Field(default=3, ge=0)
    retry_backoff_seconds: float = Field(default=2.0, gt=0)
    continue_on_error: bool = Field(default=True)
    checkpoint_path: str = Field(default="bluesky_historical_checkpoint.json")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _to_iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _status_code_from_exc(exc: Exception) -> int | None:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        return exc.response.status_code
    return None


def _three_day_windows(since: str, until: str) -> list[tuple[str, str]]:
    start = _parse_dt(since)
    end = _parse_dt(until)
    if not start or not end:
        raise ValueError("Invalid since/until datetime")
    if start >= end:
        raise ValueError("since must be earlier than until")

    windows: list[tuple[str, str]] = []
    current = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)

    while current < end:
        window_end = current + timedelta(days=3)
        if window_end > end:
            window_end = end

        windows.append((_to_iso_z(current), _to_iso_z(window_end)))
        current = window_end

    return windows


def _to_time_us(created_at: str | None, indexed_at: str | None) -> int | None:
    dt = _parse_dt(indexed_at) or _parse_dt(created_at)
    if not dt:
        return None
    return int(dt.timestamp() * 1_000_000)


def _normalise_keywords(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip().lower() for part in value.split() if part.strip()]


def _normalise_queries(queries: str | None) -> list[str]:
    if not queries:
        return DEFAULT_AU_SEARCH_QUERIES
    return [q.strip() for q in queries.split(";") if q.strip()]


def _matched_keywords(text: str | None, keywords: list[str]) -> list[str]:
    if not text or not keywords:
        return []
    lowered = text.lower()
    return [kw for kw in keywords if kw in lowered]


def _contains_keyword(text: str, keyword: str) -> bool:
    text = text.lower()
    keyword = keyword.lower()
    if " " in keyword:
        return keyword in text
    return re.search(rf"\b{re.escape(keyword)}\b", text) is not None


def _count_keyword_hits(text: str, keywords: list[str]) -> int:
    return sum(1 for kw in keywords if _contains_keyword(text, kw))


def _is_au_relevant(text: str | None) -> bool:
    if not isinstance(text, str) or not text.strip():
        return False

    strong_hits = _count_keyword_hits(text, STRONG_AU_KEYWORDS)
    medium_hits = _count_keyword_hits(text, MEDIUM_AU_KEYWORDS)
    weak_hits = _count_keyword_hits(text, WEAK_CITY_KEYWORDS)

    if strong_hits >= 1:
        return True
    if medium_hits >= 1:
        return True
    if weak_hits >= 2:
        return True
    return False


def _is_before_cutoff(created_at: str | None, cutoff_before: str) -> bool:
    created_dt = _parse_dt(created_at)
    cutoff_dt = _parse_dt(cutoff_before)
    if not created_dt or not cutoff_dt:
        return False
    return created_dt < cutoff_dt


def _compact(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            vv = _compact(v)
            if vv is None:
                continue
            if isinstance(vv, dict) and not vv:
                continue
            out[k] = vv
        return out

    if isinstance(obj, list):
        cleaned = []
        for v in obj:
            vv = _compact(v)
            if vv is not None:
                cleaned.append(vv)
        return cleaned

    return obj


@dataclass
class BlueskyHistoricalCollector:
    settings: BlueskyHistoricalSettings
    es: AsyncElasticsearch | None = None
    vk: Valkey | None = None

    def write_checkpoint(self, payload: dict[str, Any]) -> None:
        path = Path(self.settings.checkpoint_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    async def create_session(self, client: httpx.AsyncClient) -> str:
        payload = {
            "identifier": self.settings.handle,
            "password": self.settings.app_password,
        }

        resp = await client.post(
            f"{self.settings.base_url}{self.settings.create_session_endpoint}",
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

        access_jwt = data.get("accessJwt")
        if not access_jwt:
            raise RuntimeError("No accessJwt returned from createSession")

        return access_jwt

    async def fetch_page(
        self,
        client: httpx.AsyncClient,
        access_jwt: str,
        query: str,
        cursor: str | None = None,
        sort: str = "latest",
        since: str | None = None,
        until: str | None = None,
        lang: str = "en",
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "q": query,
            "limit": self.settings.page_size,
            "sort": sort,
        }
        if cursor:
            params["cursor"] = cursor
        if since:
            params["since"] = since
        if until:
            params["until"] = until
        if lang:
            params["lang"] = lang

        retryable_statuses = {429, 500, 502, 503, 504}

        for attempt in range(self.settings.max_retries + 1):
            try:
                resp = await client.get(
                    f"{self.settings.base_url}{self.settings.search_endpoint}",
                    params=params,
                    headers={"Authorization": f"Bearer {access_jwt}"},
                )

                if resp.status_code in retryable_statuses:
                    resp.raise_for_status()

                resp.raise_for_status()
                return resp.json()

            except Exception as exc:
                status_code = _status_code_from_exc(exc)
                retryable = (
                    isinstance(
                        exc, (httpx.TimeoutException, httpx.TransportError)
                    )
                    or status_code in retryable_statuses
                )

                if (not retryable) or attempt >= self.settings.max_retries:
                    raise

                wait_seconds = self.settings.retry_backoff_seconds * (
                    2**attempt
                )
                logger.warning(
                    "Retryable error for query='%s' cursor=%s since=%s until=%s "
                    "| status=%s | attempt=%s/%s | waiting %.1fs",
                    query,
                    cursor,
                    since,
                    until,
                    status_code,
                    attempt + 1,
                    self.settings.max_retries,
                    wait_seconds,
                )
                await asyncio.sleep(wait_seconds)

        raise RuntimeError("Unreachable fetch_page retry block")

    def normalise_post(
        self, post: dict[str, Any], query_keywords: list[str]
    ) -> dict[str, Any]:
        author = post.get("author") or {}
        record = post.get("record") or {}

        text = record.get("text")
        created_at = record.get("createdAt")
        uri = post.get("uri") or ""
        rkey = uri.rsplit("/", 1)[-1] if uri else None

        doc = {
            "did": author.get("did"),
            "time_us": _to_time_us(created_at, post.get("indexedAt")),
            "kind": "search",
            "identity": {
                "handle": author.get("handle"),
            },
            "commit": {
                "operation": "create",
                "collection": "app.bsky.feed.post",
                "rkey": rkey,
                "cid": post.get("cid"),
                "record": {
                    "text": text,
                    "createdAt": created_at,
                },
            },
            "matched_strong_keywords": _matched_keywords(
                text, STRONG_AU_KEYWORDS
            ),
            "matched_medium_keywords": _matched_keywords(
                text, MEDIUM_AU_KEYWORDS
            ),
            "matched_weak_keywords": _matched_keywords(
                text, WEAK_CITY_KEYWORDS
            ),
            "matched_topic_keywords": _matched_keywords(text, query_keywords),
        }

        return _compact(doc)

    def make_doc_id(self, doc: dict[str, Any]) -> str:
        did = doc.get("did") or "unknown"
        commit = doc.get("commit") or {}
        rkey = commit.get("rkey") or "unknown"
        return f"{did}:{rkey}"

    async def index_batch(self, docs: list[dict[str, Any]]) -> int:
        if not docs or self.es is None:
            return 0

        total = 0
        for doc in docs:
            doc_id = self.make_doc_id(doc)
            exists = await self.es.exists(
                index="social-posts-index", id=f"bluesky-{doc_id}"
            )
            if exists:
                continue

            to_insert = {
                "source": "bluesky",
                "data": doc,
            }
            await self.vk.lpush("social-posts-index", json.dumps(to_insert))
            await asyncio.sleep(0.032)
            total += 1

        if await self.vk.llen("social-posts-index") > 12_000:
            await asyncio.sleep(15.0)
        return total

    async def collect_query(
        self,
        client: httpx.AsyncClient,
        access_jwt: str,
        query: str,
        sort: str = "latest",
        since: str | None = None,
        until: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, int]:
        fetched = 0
        kept = 0
        indexed = 0
        pages = 0
        cursor: str | None = None
        query_keywords = _normalise_keywords(query)

        self.write_checkpoint(
            {
                "updated_at": _utc_now_iso(),
                "status": "query_started",
                "query": query,
                "since": since,
                "until": until,
                "page": 0,
                "cursor": cursor,
                "fetched": fetched,
                "kept": kept,
                "indexed": indexed,
            }
        )

        while pages < self.settings.max_pages:
            try:
                payload = await self.fetch_page(
                    client=client,
                    access_jwt=access_jwt,
                    query=query,
                    cursor=cursor,
                    sort=sort,
                    since=since,
                    until=until,
                )
            except Exception as exc:
                logger.exception(
                    "Query failed and stopped | query='%s' | since=%s | until=%s | page=%s",
                    query,
                    since,
                    until,
                    pages + 1,
                )

                self.write_checkpoint(
                    {
                        "updated_at": _utc_now_iso(),
                        "status": "query_error",
                        "query": query,
                        "since": since,
                        "until": until,
                        "page": pages + 1,
                        "cursor": cursor,
                        "fetched": fetched,
                        "kept": kept,
                        "indexed": indexed,
                        "error": str(exc),
                    }
                )

                if self.settings.continue_on_error:
                    break
                raise

            posts = payload.get("posts") or []
            if not posts:
                logger.info(
                    "No more posts returned for query '%s', stopping.", query
                )
                break

            fetched += len(posts)

            kept_docs: list[dict[str, Any]] = []
            for post in posts:
                record = post.get("record") or {}
                text = record.get("text")
                created_at = record.get("createdAt")

                if not _is_before_cutoff(
                    created_at, self.settings.cutoff_before
                ):
                    continue
                if not _is_au_relevant(text):
                    continue

                kept_docs.append(self.normalise_post(post, query_keywords))

            kept += len(kept_docs)

            if not dry_run:
                indexed += await self.index_batch(kept_docs)

            pages += 1
            cursor = payload.get("cursor")

            logger.info(
                "Query='%s' | since=%s | until=%s | page=%s | raw_posts=%s | kept=%s | indexed=%s",
                query,
                since,
                until,
                pages,
                len(posts),
                len(kept_docs),
                indexed,
            )

            self.write_checkpoint(
                {
                    "updated_at": _utc_now_iso(),
                    "status": "query_running",
                    "query": query,
                    "since": since,
                    "until": until,
                    "page": pages,
                    "cursor": cursor,
                    "fetched": fetched,
                    "kept": kept,
                    "indexed": indexed,
                }
            )

            if not cursor:
                logger.info(
                    "No cursor returned for query '%s', stopping.", query
                )
                break

            await asyncio.sleep(0.35)

        self.write_checkpoint(
            {
                "updated_at": _utc_now_iso(),
                "status": "query_finished",
                "query": query,
                "since": since,
                "until": until,
                "page": pages,
                "cursor": cursor,
                "fetched": fetched,
                "kept": kept,
                "indexed": indexed,
            }
        )

        return {
            "pages": pages,
            "fetched": fetched,
            "kept": kept,
            "indexed": indexed,
        }

    async def collect_window(
        self,
        client: httpx.AsyncClient,
        access_jwt: str,
        queries: list[str],
        since: str,
        until: str,
        sort: str = "latest",
        dry_run: bool = False,
    ) -> dict[str, int]:
        total_pages = 0
        total_fetched = 0
        total_kept = 0
        total_indexed = 0

        logger.info("Starting window since=%s until=%s", since, until)

        self.write_checkpoint(
            {
                "updated_at": _utc_now_iso(),
                "status": "window_started",
                "since": since,
                "until": until,
                "queries": queries,
                "pages": 0,
                "fetched": 0,
                "kept": 0,
                "indexed": 0,
            }
        )

        for query in queries:
            try:
                result = await self.collect_query(
                    client=client,
                    access_jwt=access_jwt,
                    query=query,
                    sort=sort,
                    since=since,
                    until=until,
                    dry_run=dry_run,
                )
            except Exception as exc:
                logger.exception(
                    "Unexpected query failure | query='%s' | since=%s | until=%s",
                    query,
                    since,
                    until,
                )

                self.write_checkpoint(
                    {
                        "updated_at": _utc_now_iso(),
                        "status": "window_query_error",
                        "since": since,
                        "until": until,
                        "query": query,
                        "pages": total_pages,
                        "fetched": total_fetched,
                        "kept": total_kept,
                        "indexed": total_indexed,
                        "error": str(exc),
                    }
                )

                if self.settings.continue_on_error:
                    continue
                raise

            total_pages += result["pages"]
            total_fetched += result["fetched"]
            total_kept += result["kept"]
            total_indexed += result["indexed"]

        logger.info(
            "Finished window since=%s until=%s | pages=%s | fetched=%s | kept=%s | indexed=%s",
            since,
            until,
            total_pages,
            total_fetched,
            total_kept,
            total_indexed,
        )

        self.write_checkpoint(
            {
                "updated_at": _utc_now_iso(),
                "status": "window_finished",
                "since": since,
                "until": until,
                "pages": total_pages,
                "fetched": total_fetched,
                "kept": total_kept,
                "indexed": total_indexed,
            }
        )

        return {
            "pages": total_pages,
            "fetched": total_fetched,
            "kept": total_kept,
            "indexed": total_indexed,
        }

    async def collect(
        self,
        queries: list[str],
        sort: str = "latest",
        since: str | None = None,
        until: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, int]:
        if since and until and self.settings.split_by_3day:
            windows = _three_day_windows(since, until)
        else:
            windows = [(since, until)]

        total_queries = 0
        total_windows = 0
        total_pages = 0
        total_fetched = 0
        total_kept = 0
        total_indexed = 0

        async with httpx.AsyncClient(
            timeout=self.settings.timeout_seconds,
            headers={"User-Agent": self.settings.user_agent},
        ) as client:
            access_jwt = await self.create_session(client)

            for window_since, window_until in windows:
                result = await self.collect_window(
                    client=client,
                    access_jwt=access_jwt,
                    queries=queries,
                    since=window_since,
                    until=window_until,
                    sort=sort,
                    dry_run=dry_run,
                )
                total_queries += len(queries)
                total_windows += 1
                total_pages += result["pages"]
                total_fetched += result["fetched"]
                total_kept += result["kept"]
                total_indexed += result["indexed"]

        return {
            "windows": total_windows,
            "queries": total_queries,
            "pages": total_pages,
            "fetched": total_fetched,
            "kept": total_kept,
            "indexed": total_indexed,
        }


async def search_and_index(
    queries: str | None = None,
    max_pages: int | None = None,
    page_size: int | None = None,
    sort: str = "latest",
    since: str | None = None,
    until: str | None = None,
    dry_run: bool = False,
):
    hist_settings = BlueskyHistoricalSettings()

    if max_pages is not None:
        hist_settings.max_pages = max_pages
    if page_size is not None:
        hist_settings.page_size = page_size

    query_list = _normalise_queries(queries)

    if dry_run:
        collector = BlueskyHistoricalCollector(hist_settings, es=None)
        return await collector.collect(
            queries=query_list,
            sort=sort,
            since=since,
            until=until,
            dry_run=True,
        )

    es_settings = ESSettings()
    async with AsyncElasticsearch(
        es_settings.host,
        api_key=es_settings.api_key,
        verify_certs=False,
    ) as es:
        vk = Valkey()
        collector = BlueskyHistoricalCollector(hist_settings, es, vk)
        return await collector.collect(
            queries=query_list,
            sort=sort,
            since=since,
            until=until,
            dry_run=False,
        )


def run(
    queries: str | None = None,
    max_pages: int | None = None,
    page_size: int | None = None,
    sort: str = "latest",
    since: str | None = None,
    until: str | None = None,
    dry_run: bool = False,
):
    return asyncio.run(
        search_and_index(
            queries=queries,
            max_pages=max_pages,
            page_size=page_size,
            sort=sort,
            since=since,
            until=until,
            dry_run=dry_run,
        )
    )


if __name__ == "__main__":
    fire.Fire({"search": run})
