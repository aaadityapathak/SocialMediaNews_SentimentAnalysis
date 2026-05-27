MAX_VIDEOS_PER_QUERY = 30
MAX_COMMENTS_PER_VIDEO = 50
MAX_REPLIES_PER_COMMENT = 20

LOCATIONS = [
    "australia",
    "sydney",
    "melbourne",
    "brisbane",
    "perth",
    "adelaide",
    "canberra",
]

EVENTS_SEARCH_QUERIES = {
    "events": [
        "AFL grand final australia",
        "australian open tennis",
        "australia music festival",
        "australia comedy festival",
        "formula 1 australia grand prix",
        "australia cultural festival",
        *[f"{loc} events" for loc in LOCATIONS],
        *[f"{loc} sports events" for loc in LOCATIONS],
    ]
}

AI_CONCERN_SEARCH_QUERIES = {
    "ai_concern": [
        "AI deepfake australia",
        "artificial intelligence misinformation australia",
        "fake AI generated content australia",
        "AI regulation australia",
        "AI jobs impact australia",
        "ChatGPT concerns australia",
        "AI ethics australia government",
        *[f"AI {loc}" for loc in LOCATIONS],
    ]
}

WEATHER_CLIMATE_SEARCH_QUERIES = {
    "weather_climate": [
        "australia extreme weather",
        "australia bushfire season",
        "australia floods",
        "climate change impact australia",
        "australia heatwave",
        "great barrier reef climate australia",
        "australia renewable energy",
        *[f"{loc} weather forecast" for loc in LOCATIONS],
        *[f"{loc} extreme weather" for loc in LOCATIONS],
    ]
}

POLITICS_QUERIES = {
    "politics": [
        "australian politics",
        "australia geopolitics",
        "australian elections",
        "australian cost of living",
        "cost of living crisis australia",
        "housing melbourne",
        "housing sydney",
        "affordability australia",
        "auspol",
        "ausvotes",
        "australian government",
        "australia voting",
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
        "cost of living australia",
        "housing australia",
    ]
}


SEARCH_QUERIES = POLITICS_QUERIES
