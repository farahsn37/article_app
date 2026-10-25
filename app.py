import logging
import os
from math import ceil
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request
from newspaper import Article

# --------------------------------------------------
# INITIAL CONFIGURATION
# --------------------------------------------------

load_dotenv()

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "").strip()
NEWSAPI_COUNTRY = os.getenv("NEWSAPI_COUNTRY", "us").strip().lower()

NEWSAPI_URL = "https://newsapi.org/v2/top-headlines"

# Display four articles per page
NEWSAPI_PAGE_SIZE = 4

# Maximum page number allowed
MAX_PAGE = 100

# Supported NewsAPI categories
ALLOWED_CATEGORIES = {
    "general",
    "business",
    "entertainment",
    "health",
    "science",
    "sports",
    "technology",
}


# --------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------

def truncate_text(text, max_length=200):
    """Shorten text to a specified length."""

    if not text:
        return ""

    text = " ".join(str(text).split())

    if len(text) <= max_length:
        return text

    return text[:max_length].rsplit(" ", 1)[0] + "..."


def valid_http_url(url):
    """Check whether a URL uses HTTP or HTTPS."""

    if not url:
        return False

    try:
        parsed_url = urlparse(url)

        return (
            parsed_url.scheme in {"http", "https"}
            and bool(parsed_url.netloc)
        )

    except (ValueError, TypeError):
        return False


def safe_image_url(url):
    """Return an image URL only if it is a valid HTTP(S) URL."""

    if valid_http_url(url):
        return url

    return None


def extract_article_content(url):
    """
    Attempt to extract an article's title, text, author,
    and top image using Newspaper3k.
    """

    if not valid_http_url(url):
        return {
            "title": "",
            "text": "",
            "author": "",
            "image": None,
        }

    try:
        article = Article(url)
        article.download()
        article.parse()

        return {
            "title": article.title or "",
            "text": article.text or "",
            "author": ", ".join(article.authors)
            if article.authors
            else "",
            "image": safe_image_url(article.top_image),
        }

    except Exception as exc:
        logging.warning(
            "Could not extract article content from %s: %s",
            url,
            exc,
        )

        return {
            "title": "",
            "text": "",
            "author": "",
            "image": None,
        }


# --------------------------------------------------
# FETCH ARTICLES FROM NEWSAPI
# --------------------------------------------------

def fetch_news(topic="general", query="", page=1):
    """
    Fetch articles from NewsAPI based on topic, keyword,
    and page number.

    Returns:
        displayed_articles: list of article dictionaries
        error: error message or None
        total_results: total results reported by NewsAPI
    """

    displayed_articles = []

    # Ensure the selected topic is supported
    if topic not in ALLOWED_CATEGORIES:
        topic = "general"

    # Ensure the page number is valid
    page = max(1, min(page, MAX_PAGE))

    # Ensure the keyword is a string
    query = query.strip() if query else ""

    # Check whether the API key is configured
    if not NEWSAPI_KEY:
        return (
            [],
            "NewsAPI key is missing. Please configure NEWSAPI_KEY in your .env file.",
            0,
        )

    # NewsAPI request parameters
    params = {
        "country": NEWSAPI_COUNTRY,
        "category": topic,
        "page": page,
        "pageSize": NEWSAPI_PAGE_SIZE,
    }

    # Add keyword search if the user entered one
    if query:
        params["q"] = query

    headers = {
        "X-Api-Key": NEWSAPI_KEY,
    }

    try:
        response = requests.get(
            NEWSAPI_URL,
            headers=headers,
            params=params,
            timeout=15,
        )

        response.raise_for_status()

        data = response.json()

        # Check NewsAPI response status
        if data.get("status") != "ok":
            message = data.get(
                "message",
                "Unable to retrieve articles from NewsAPI.",
            )

            return [], message, 0

        # Total number of results reported by NewsAPI
        total_results = data.get("totalResults", 0)

        articles = data.get("articles", [])

        # Process each article
        for item in articles:

            url = item.get("url")

            # Skip articles without a valid URL
            if not valid_http_url(url):
                continue

            source_info = item.get("source") or {}

            source_name = source_info.get("name") or "Unknown Source"

            published_at = item.get("publishedAt") or ""

            api_title = item.get("title") or "Untitled Article"

            description = item.get("description") or ""

            api_content = item.get("content") or ""

            api_author = item.get("author") or ""

            api_image = safe_image_url(item.get("urlToImage"))

            # Attempt to extract the article content
            extracted = extract_article_content(url)

            title = extracted["title"] or api_title

            content = (
                extracted["text"]
                or api_content
                or description
            )

            author = extracted["author"] or api_author or "Unknown"

            image_url = extracted["image"] or api_image

            # Prepare the article for the frontend
            article_data = {
                "id": len(displayed_articles) + 1,
                "title": title,
                "category": topic.title(),
                "author": author,
                "summary": truncate_text(
                    description or content,
                    180,
                ),
                "image": image_url,
                "content": truncate_text(content, 600),
                "preview": truncate_text(content, 220),
                "url": url,
                "source": source_name,
                "published_at": published_at,
            }

            displayed_articles.append(article_data)

        return displayed_articles, None, total_results

    except requests.exceptions.HTTPError as exc:
        logging.error("NewsAPI HTTP error: %s", exc)

        try:
            error_data = response.json()
            error_message = error_data.get(
                "message",
                "NewsAPI returned an HTTP error.",
            )
        except ValueError:
            error_message = "NewsAPI returned an HTTP error."

        return [], error_message, 0

    except requests.exceptions.Timeout:
        logging.error("NewsAPI request timed out.")

        return (
            [],
            "The request to NewsAPI timed out. Please try again.",
            0,
        )

    except requests.exceptions.RequestException as exc:
        logging.error("NewsAPI request failed: %s", exc)

        return (
            [],
            "Unable to connect to NewsAPI. Please try again later.",
            0,
        )

    except (ValueError, TypeError) as exc:
        logging.error("Invalid NewsAPI response: %s", exc)

        return (
            [],
            "The response from NewsAPI could not be processed.",
            0,
        )


# --------------------------------------------------
# HOME PAGE: TOPIC FILTERING AND PAGINATION
# --------------------------------------------------

@app.route("/")
def index():

    # Read the selected topic from the URL
    topic = request.args.get(
        "topic",
        "general",
    ).strip().lower()

    # Read the search keyword
    query = request.args.get(
        "query",
        "",
    ).strip()

    # Validate the topic
    if topic not in ALLOWED_CATEGORIES:
        topic = "general"

    # Read and validate the requested page
    try:
        page = int(request.args.get("page", 1))
    except (ValueError, TypeError):
        page = 1

    page = max(1, min(page, MAX_PAGE))

    # Fetch articles using the selected topic and page
    articles, error, total_results = fetch_news(
        topic=topic,
        query=query,
        page=page,
    )

    # Calculate the total pages from NewsAPI's result count
    total_pages = min(
        MAX_PAGE,
        ceil(total_results / NEWSAPI_PAGE_SIZE),
    )

    return render_template(
        "index.html",
        articles=articles,
        error=error,
        topic=topic,
        query=query,
        page=page,
        total_pages=total_pages,
    )


# --------------------------------------------------
# RUN FLASK APPLICATION
# --------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)