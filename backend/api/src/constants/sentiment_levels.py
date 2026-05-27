class SentimentLevels:
    LEVELS: dict[str, list[str]] = {
        # TODO: check by similarity of word in analytics or ml modules
        "love": [
            "love",
            "loved",
            "loves",
            "adore",
            "amazing",
            "awesome",
            "fantastic",
            "brilliant",
            "wonderful",
            "excellent",
            "perfect",
            "best",
        ],
        "good": [
            "good",
            "nice",
            "decent",
            "ok",
            "okay",
            "fine",
            "comfortable",
            "convenient",
            "happy",
            "pleasant",
            "smooth",
            "reliable",
        ],
        "concern": [
            "concern",
            "concerned",
            "worry",
            "worried",
            "issue",
            "issues",
            "problem",
            "problems",
            "delay",
            "delayed",
            "slow",
            "crowded",
            "packed",
            "expensive",
            "pricey",
        ],
        "bad": [
            "bad",
            "poor",
            "annoying",
            "frustrating",
            "awful",
            "terrible",
            "worse",
            "unreliable",
            "broken",
            "late",
            "rubbish",
        ],
        "hate": [
            "hate",
            "hated",
            "loathe",
            "horrible",
            "disaster",
            "nightmare",
            "useless",
            "worst",
            "despise",
            "garbage",
            "trash",
        ],
    }

    @classmethod
    def names(cls) -> list[str]:
        return list(cls.LEVELS.keys())

    @classmethod
    def keywords(cls, name: str) -> list[str]:
        return cls.LEVELS[name]

    @classmethod
    def query(cls, name: str) -> str:
        return " | ".join(cls.LEVELS[name])

    @classmethod
    def as_queries(cls) -> dict[str, str]:
        return {name: cls.query(name) for name in cls.LEVELS}
