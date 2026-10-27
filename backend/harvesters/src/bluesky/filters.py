"""Reusable Australian relevance and topic matching for Bluesky posts."""

import re
from functools import lru_cache

# Strong signals: if any of these appear, the post is very likely AU-related
STRONG_AU_KEYWORDS = [
    "australia",
    "australian",
    "aussie",
    "aussies",
    "auspol",
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
]

# Medium signals: AU-specific enough to accept directly, but not as strong as the group above
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
    "australian labor party",
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
    "cozzielife",
]


# Weak signals: city names or ambiguous terms; require at least two weak hits if no strong/medium hit
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
    "albanese",
    "dutton",
    "pauline hanson",
    "alp",
    "nlp",
    "labor party",
    "cost of living",
    "housing crisis",
    "cozzie",
]


def normalise_keywords(keywords: list[str] | None) -> list[str]:
    if not keywords:
        return []
    return [kw.strip().lower() for kw in keywords if kw and kw.strip()]


@lru_cache(maxsize=512)
def _keyword_pattern(keyword: str) -> re.Pattern:
    return re.compile(rf"\b{re.escape(keyword)}\b", re.IGNORECASE)


def contains_keyword(text: str, keyword: str) -> bool:
    text = text.lower()
    keyword = keyword.lower()

    # multi-word phrase: use normal substring match
    if " " in keyword:
        return keyword in text

    # short abbreviation: require whole word match
    return _keyword_pattern(keyword).search(text) is not None


def count_keyword_hits(text: str, keywords: list[str]) -> int:
    return sum(1 for kw in keywords if contains_keyword(text, kw))


def is_au_relevant(text: str | None) -> bool:
    """
    Broad Australia relevance filter.

    Rules:
    - any strong AU signal -> accept
    - any medium AU signal -> accept
    - otherwise require at least 2 weak city/location signals
    """
    if not isinstance(text, str) or not text.strip():
        return False

    if any(contains_keyword(text, kw) for kw in STRONG_AU_KEYWORDS):
        return True
    if any(contains_keyword(text, kw) for kw in MEDIUM_AU_KEYWORDS):
        return True
    hits = 0
    for kw in WEAK_CITY_KEYWORDS:
        if contains_keyword(text, kw):
            hits += 1
            if hits == 2:
                return True
    return False


def matches_topic_keywords(
    text: str | None, keywords: list[str] | None
) -> bool:
    """
    Optional second-stage topic filter.
    Example use cases:
    - transport-related terms
    - policy-related terms
    """
    if not keywords:
        return True

    if not isinstance(text, str) or not text.strip():
        return False

    lowered = text.lower()
    topic_keywords = normalise_keywords(keywords)
    return any(kw in lowered for kw in topic_keywords)


def get_matched_keywords(text: str | None, keywords: list[str]) -> list[str]:
    if not isinstance(text, str) or not text.strip():
        return []

    return [kw for kw in keywords if contains_keyword(text, kw)]
