class TransportGroups:
    GROUPS: dict[str, list[str]] = {
        "car_traffic": [
            "car",
            "cars",
            "driving",
            "driver",
            "drivers",
            "road",
            "roads",
            "traffic",
            "congestion",
            "parking",
            "commute",
            "commuting",
        ],
        "rail_train": [
            "train",
            "trains",
            "rail",
            "railway",
            "metro",
            "station",
            "stations",
            "platform",
        ],
        "bus_tram_fares": [
            "bus",
            "buses",
            "tram",
            "trams",
            "fare",
            "fares",
            "myki",
            "commuter",
            "commuters",
            "patronage",
        ],
        "active_transport": [
            "bike",
            "bikes",
            "bicycle",
            "bicycles",
            "cycling",
            "cyclist",
            "cyclists",
            "walk",
            "walking",
            "pedestrian",
            "pedestrians",
        ],
    }

    @classmethod
    def names(cls) -> list[str]:
        return list(cls.GROUPS.keys())

    @classmethod
    def keywords(cls, name: str) -> list[str]:
        return cls.GROUPS[name]

    @classmethod
    def query(cls, name: str) -> str:
        return " | ".join(cls.GROUPS[name])

    @classmethod
    def as_queries(cls) -> dict[str, str]:
        return {name: cls.query(name) for name in cls.GROUPS}
