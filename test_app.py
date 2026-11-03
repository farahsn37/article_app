
import pytest
import requests
import app as news_app


# --------------------------------------------------
# HELPER: MOCK NEWSAPI RESPONSE
# --------------------------------------------------

class MockResponse:

    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


# Sample article returned by NewsAPI
SAMPLE_ARTICLE = {
    "source": {"id": None, "name": "BBC News"},
    "author": "John Smith",
    "title": "Technology News Today",
    "description": "Latest technology developments.",
    "url": "https://example.com/news",
    "urlToImage": "https://example.com/image.jpg",
    "publishedAt": "2026-11-01T10:00:00Z",
    "content": "Technology news content [+chars]"
}


# --------------------------------------------------
# UT-01: SUCCESSFUL NEWS RETRIEVAL
# --------------------------------------------------

def test_fetch_news_successfully(monkeypatch):

    monkeypatch.setattr(news_app, "NEWSAPI_KEY", "test_api_key")

    monkeypatch.setattr(
        news_app.requests,
        "get",
        lambda *args, **kwargs: MockResponse({
            "status": "ok",
            "totalResults": 1,
            "articles": [SAMPLE_ARTICLE]
        })
    )

    monkeypatch.setattr(
        news_app,
        "extract_article_details",
        lambda url: {}
    )

    articles, error, total = news_app.fetch_news()

    assert len(articles) == 1
    assert error is None
    assert total == 1
    assert articles[0]["title"] == "Technology News Today"
    assert articles[0]["source"] == "BBC News"


# --------------------------------------------------
# UT-02: MISSING API KEY
# --------------------------------------------------

def test_fetch_news_without_api_key(monkeypatch):

    monkeypatch.setattr(news_app, "NEWSAPI_KEY", None)

    articles, error, total = news_app.fetch_news()

    assert articles == []
    assert error is not None
    assert "API key is missing" in error
    assert total == 0


# --------------------------------------------------
# UT-03: INVALID CATEGORY
# --------------------------------------------------

def test_fetch_news_with_invalid_category(monkeypatch):

    monkeypatch.setattr(news_app, "NEWSAPI_KEY", "test_api_key")

    captured = {}

    def mock_get(url, params, timeout):

        captured.update(params)

        return MockResponse({
            "status": "ok",
            "totalResults": 0,
            "articles": []
        })

    monkeypatch.setattr(news_app.requests, "get", mock_get)

    articles, error, total = news_app.fetch_news(
        topic="invalid_category"
    )

    assert captured["category"] == "general"
    assert error is None
    assert articles == []


# --------------------------------------------------
# UT-04: INVALID PAGE NUMBER
# --------------------------------------------------

def test_fetch_news_with_invalid_page(monkeypatch):

    monkeypatch.setattr(news_app, "NEWSAPI_KEY", "test_api_key")

    captured = {}

    def mock_get(url, params, timeout):

        captured.update(params)

        return MockResponse({
            "status": "ok",
            "totalResults": 0,
            "articles": []
        })

    monkeypatch.setattr(news_app.requests, "get", mock_get)

    news_app.fetch_news(page="invalid")

    assert captured["page"] == 1


# --------------------------------------------------
# UT-05: KEYWORD SEARCH
# --------------------------------------------------

def test_fetch_news_with_keyword(monkeypatch):

    monkeypatch.setattr(news_app, "NEWSAPI_KEY", "test_api_key")

    captured = {}

    def mock_get(url, params, timeout):

        captured.update(params)

        return MockResponse({
            "status": "ok",
            "totalResults": 0,
            "articles": []
        })

    monkeypatch.setattr(news_app.requests, "get", mock_get)

    news_app.fetch_news(query="Artificial Intelligence")

    assert captured["q"] == "Artificial Intelligence"


# --------------------------------------------------
# UT-06: EMPTY API RESPONSE
# --------------------------------------------------

def test_fetch_news_with_no_articles(monkeypatch):

    monkeypatch.setattr(news_app, "NEWSAPI_KEY", "test_api_key")

    monkeypatch.setattr(
        news_app.requests,
        "get",
        lambda *args, **kwargs: MockResponse({
            "status": "ok",
            "totalResults": 0,
            "articles": []
        })
    )

    articles, error, total = news_app.fetch_news()

    assert articles == []
    assert error is None
    assert total == 0


# --------------------------------------------------
# UT-07: NEWSAPI TIMEOUT
# --------------------------------------------------

def test_fetch_news_timeout(monkeypatch):

    monkeypatch.setattr(news_app, "NEWSAPI_KEY", "test_api_key")

    def mock_get(*args, **kwargs):
        raise requests.exceptions.Timeout()

    monkeypatch.setattr(news_app.requests, "get", mock_get)

    articles, error, total = news_app.fetch_news()

    assert articles == []
    assert "timed out" in error
    assert total == 0


# --------------------------------------------------
# UT-08: INVALID ARTICLE URL
# --------------------------------------------------

def test_fetch_news_with_invalid_article_url(monkeypatch):

    monkeypatch.setattr(news_app, "NEWSAPI_KEY", "test_api_key")

    article = SAMPLE_ARTICLE.copy()
    article["url"] = "invalid-url"

    monkeypatch.setattr(
        news_app.requests,
        "get",
        lambda *args, **kwargs: MockResponse({
            "status": "ok",
            "totalResults": 1,
            "articles": [article]
        })
    )

    monkeypatch.setattr(
        news_app,
        "extract_article_details",
        lambda url: {}
    )

    articles, error, total = news_app.fetch_news()

    assert len(articles) == 1
    assert articles[0]["url"] == ""
    assert error is None


# --------------------------------------------------
# UT-09: ARTICLE EXTRACTION FAILURE
# --------------------------------------------------

def test_fetch_news_when_extraction_fails(monkeypatch):

    monkeypatch.setattr(news_app, "NEWSAPI_KEY", "test_api_key")

    monkeypatch.setattr(
        news_app.requests,
        "get",
        lambda *args, **kwargs: MockResponse({
            "status": "ok",
            "totalResults": 1,
            "articles": [SAMPLE_ARTICLE]
        })
    )

    monkeypatch.setattr(
        news_app,
        "extract_article_details",
        lambda url: {}
    )

    articles, error, total = news_app.fetch_news()

    assert len(articles) == 1
    assert articles[0]["title"] == "Technology News Today"
    assert articles[0]["summary"] == "Latest technology developments."
    assert error is None


# --------------------------------------------------
# UT-10: MISSING ARTICLE INFORMATION
# --------------------------------------------------

def test_fetch_news_with_missing_information(monkeypatch):

    monkeypatch.setattr(news_app, "NEWSAPI_KEY", "test_api_key")

    incomplete_article = {
        "url": "https://example.com/news"
    }

    monkeypatch.setattr(
        news_app.requests,
        "get",
        lambda *args, **kwargs: MockResponse({
            "status": "ok",
            "totalResults": 1,
            "articles": [incomplete_article]
        })
    )

    monkeypatch.setattr(
        news_app,
        "extract_article_details",
        lambda url: {}
    )

    articles, error, total = news_app.fetch_news()

    assert len(articles) == 1
    assert articles[0]["title"] == "Title unavailable"
    assert articles[0]["author"] == "Unknown"
    assert articles[0]["source"] == "Unknown source"
    assert articles[0]["summary"] == "No summary is available for this article."
