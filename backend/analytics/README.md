# Analytics module

Text analytics module provides sentiment analysis and keyword extraction over harvested social media posts.

## Features

- **Sentiment analysis** via VADER (compound score + pos/neg/neu breakdown) and TextBlob (subjectivity)
- **Keyword extraction** using NLTK tokenisation and frequency distribution with stopword filtering

## Setup
Requires [uv](https://docs.astral.sh/uv/). From the repo root:

```bash
uv sync
```

Or install just this workspace member:

```bash
uv sync --package analytics
```

## Usage

1. Import clas
```python
from data_extractor import TextExtractor

extractor = TextExtractor()

result = extractor.analyse("Australia is facing record heatwaves this summer.")
print(result.sentiment.label)
print(result.sentiment.score)
print(result.keywords)

sentiment = extractor.sentiment("Protests erupt across Sydney CBD.")
keywords = extractor.keywords("The Great Barrier Reef bleaching event worsens.", top_n=5)
```
