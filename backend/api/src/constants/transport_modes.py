class TransportModes:
    MODES: dict[str, list[str]] = {
        # TODO: check by similarity of word in analytics or ml modules
        "car": [
            "car",
            "cars",
            "driving",
            "driver",
            "drivers",
        ],
        "bike": [
            "bike",
            "bikes",
            "bicycle",
            "bicycles",
            "cycling",
            "cyclist",
            "cyclists",
        ],
        "tram": [
            "tram",
            "trams",
        ],
        "train": [
            "train",
            "trains",
            "rail",
            "railway",
            "metro",
        ],
        "bus": [
            "bus",
            "buses",
        ],
        "ferry": [
            "ferry",
            "ferries",
        ],
        "walk": [
            "walk",
            "walking",
            "pedestrian",
            "pedestrians",
        ],
    }

    @classmethod
    def names(cls) -> list[str]:
        return list(cls.MODES.keys())

    @classmethod
    def keywords(cls, name: str) -> list[str]:
        return cls.MODES[name]

    @classmethod
    def query(cls, name: str) -> str:
        return " | ".join(cls.MODES[name])

    @classmethod
    def as_queries(cls) -> dict[str, str]:
        return {name: cls.query(name) for name in cls.MODES}
