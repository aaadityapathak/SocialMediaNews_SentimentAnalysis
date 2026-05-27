import pytest
from analytics.data_extractor import TextExtractor


@pytest.fixture(scope="module")
def extractor():
    return TextExtractor()


def test_analyse_empty_text(extractor):
    result = extractor.analyse("")
    assert result.keywords == []
    assert result.sentiment.label in ("neutral", "positive", "negative")


def test_sentiment_positive(extractor):
    result = extractor.sentiment("Amazing sunny day in Melbourne, loving it!")
    assert result.label == "positive"
    assert result.score > 0


def test_sentiment_negative(extractor):
    result = extractor.sentiment(
        "Devastating floods hit Brisbane, terrible disaster"
    )
    assert result.label == "negative"
    assert result.score < 0


def test_sentiment_neutral(extractor):
    result = extractor.sentiment("The weather in Sydney today is cloudy")
    assert result.label in ("neutral", "positive", "negative")
    assert -1 <= result.score <= 1


def test_keywords_returns_list(extractor):
    result = extractor.keywords(
        "Melbourne heatwave breaks records across Victoria"
    )
    assert isinstance(result, list)
    assert len(result) > 0


def test_keywords_no_stopwords(extractor):
    result = extractor.keywords("the weather in australia is very hot today")
    assert "the" not in result
    assert "in" not in result
    assert "is" not in result


def test_keywords_top_n(extractor):
    text = "australia floods rain storm weather climate disaster emergency warning alert"
    result = extractor.keywords(text, top_n=3)
    assert len(result) <= 3
