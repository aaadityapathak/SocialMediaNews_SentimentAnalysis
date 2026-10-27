import logging

from nltk import FreqDist
from nltk.corpus import stopwords
from nltk.sentiment.vader import SentimentIntensityAnalyzer
from nltk.tokenize import word_tokenize
from pydantic import BaseModel
from textblob import TextBlob

log = logging.getLogger(__name__)


class SentimentResult(BaseModel):
    label: str
    score: float
    positive: float
    negative: float
    neutral: float
    subjectivity: float


class AnalysisResult(BaseModel):
    sentiment: SentimentResult
    keywords: list[str]


class TextExtractor:
    def __init__(self) -> None:
        self._vader = SentimentIntensityAnalyzer()
        self._stopwords = set(stopwords.words("english"))

    def _sentiment_vader(self, text: str) -> SentimentResult:
        scores = self._vader.polarity_scores(text)
        compound = scores["compound"]
        if compound >= 0.05:
            label = "positive"
        elif compound <= -0.05:
            label = "negative"
        else:
            label = "neutral"
        subjectivity = TextBlob(text).sentiment.subjectivity
        return SentimentResult(
            label=label,
            score=round(compound, 4),
            positive=round(scores["pos"], 4),
            negative=round(scores["neg"], 4),
            neutral=round(scores["neu"], 4),
            subjectivity=round(subjectivity, 4),
        )

    def sentiment(self, text: str) -> SentimentResult:
        return self._sentiment_vader(text)

    def keywords(self, text: str, top_n: int = 10) -> list[str]:
        tokens = [
            t.lower()
            for t in word_tokenize(text)
            if t.isalpha() and t.lower() not in self._stopwords and len(t) > 2
        ]
        if not tokens:
            return []
        return [word for word, _ in FreqDist(tokens).most_common(top_n)]

    def analyse(self, text: str, top_keywords: int = 10) -> AnalysisResult:
        return AnalysisResult(
            sentiment=self.sentiment(text),
            keywords=self.keywords(text, top_n=top_keywords),
        )
