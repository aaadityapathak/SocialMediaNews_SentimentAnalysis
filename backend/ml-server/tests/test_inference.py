def test_sentiment_analysis_method(inference_service):
    """
    Basic test for sentiment analysis to make sure method runs
    :param inference_service:
    :return:
    """
    t1 = "This is a great and very positive text!"
    result = inference_service.perform_sentiment_analysis(t1)

    assert isinstance(result, dict)
    assert "positive" in result and "negative" in result and "neutral" in result


def test_embed_method(inference_service):
    """
    Test that the text embedding method runs correctly
    :param inference_service:
    :return:
    """
    t1 = "This is a great and very positive text!"
    result = inference_service.embed_text(t1)
    assert isinstance(result, list)
    assert all(isinstance(e, float) for e in result)


def test_emotion_method(inference_service):
    """
    Test that the emotion detection method runs correctly
    :param inference_service:
    :return:
    """
    t1 = "This is a great and very positive text!"
    result = inference_service.perform_emotion_detection(t1, threshold=0.3)
    assert isinstance(result, list)
    assert all("label" in e and "score" in e for e in result)
    assert all(e["score"] >= 0.3 for e in result)
