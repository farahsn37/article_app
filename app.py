import logging
import math
import os
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request
from newspaper import Article

# ==========================================================
# CONFIGURATION
# ==========================================================

load_dotenv()

app = Flask(__name__)

# Configure logging so we can see how many articles
# NewsAPI returns in the terminal.
logging.basicConfig(level=logging.INFO)

NEWSAPI_URL = "https://newsapi.org/v2/top-headlines"

# Number of articles requested per page.
NEWSAPI_PAGE_SIZE = 4

# NewsAPI allows a maximum of 100 results per request.
MAX_PAGE = 100

# Read the API key from the .env file.
NEWSAPI_KEY = (
    os.getenv("NEWSAPI_KEY")
    or os.getenv("NEWS_API_KEY")
)

# Country code, for example: us, gb, au.
NEWSAPI_COUNTRY = os.getenv("NEWSAPI_COUNTRY", "us").lower()

# Supported news categories.
ALLOWED_CATEGORIES = {
    "general",
    "business",
    "entertainment",
    "health",
    "science",
    "sports",
    "technology",
}


# ==========================================================
# URL VALIDATION
# ==========================================================

def valid_http_url(url):
    """
    Check whether a URL is a valid HTTP or HTTPS URL.

    Returns True for valid web URLs and False otherwise.
    """

    if not url or not isinstance(url, str):
        return False

    try:
        parsed_url = urlparse(url)

        return (
            parsed_url.scheme in {"http", "https"}
            and bool(parsed_url.netloc)
        )

    except (TypeError, ValueError):
        return False


# ==========================================================
# ARTICLE EXTRACTION
# ==========================================================

def extract_article_details(url):
    """
    Attempt to extract additional article details using
    Newspaper3k.

    If extraction fails, return an empty dictionary.
    The article itself will still be displayed using
    the information supplied by NewsAPI.
    """

    if not valid_http_url(url):
        return {}

    try:
        article = Article(url)

        article.download()
        article.parse()

        details = {}

        if article.title:
            details["title"] = article.title.strip()

        if article.text:
            details["text"] = article.text.strip()

        if article.summary:
            details["summary"] = article.summary.strip()

        if article.authors:
            details["author"] = ", ".join(article.authors)

        if article.top_image:
            details["image"] = article.top_image

        return details

    except Exception as error:
        logging.warning(
            "Newspaper3k could not extract article details: %s",
            error,
        )

        return {}


# ==========================================================
# FETCH NEWS FROM NEWSAPI
# ==========================================================

def fetch_news(topic="general", query="", page=1):
    """
    Retrieve news articles from NewsAPI.

    Returns:
        displayed_articles: List of article dictionaries.
        error: Error message or None.
        total_results: Total number of results reported by NewsAPI.
    """

    displayed_articles = []
    error = None
    total_results = 0

    # ------------------------------------------------------
    # 1. Check API key
    # ------------------------------------------------------

    if not NEWSAPI_KEY:
        error = (
            "NewsAPI key is missing. "
            "Please configure NEWSAPI_KEY in your .env file."
        )

        logging.error(error)

        return displayed_articles, error, total_results

    # ------------------------------------------------------
    # 2. Validate category
    # ------------------------------------------------------

    topic = (topic or "general").strip().lower()

    if topic not in ALLOWED_CATEGORIES:
        topic = "general"

    # ------------------------------------------------------
    # 3. Validate page number
    # ------------------------------------------------------

    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 1

    page = max(1, min(page, MAX_PAGE))

    # ------------------------------------------------------
    # 4. Prepare NewsAPI request parameters
    # ------------------------------------------------------

    params = {
        "country": NEWSAPI_COUNTRY,
        "category": topic,
        "page": page,
        "pageSize": NEWSAPI_PAGE_SIZE,
        "apiKey": NEWSAPI_KEY,
    }

    # Add the search keyword if the user entered one.
    if query:
        params["q"] = query.strip()

    # ------------------------------------------------------
    # 5. Send request to NewsAPI
    # ------------------------------------------------------

    try:
        response = requests.get(
            NEWSAPI_URL,
            params=params,
            timeout=15,
        )

        # Raise an exception if the HTTP request failed.
        response.raise_for_status()

        data = response.json()

        # NewsAPI can return an error in its JSON response.
        if data.get("status") != "ok":
            error = data.get(
                "message",
                "NewsAPI could not retrieve the articles.",
            )

            logging.error("NewsAPI error: %s", error)

            return displayed_articles, error, total_results

        # --------------------------------------------------
        # 6. Retrieve articles from the API response
        # --------------------------------------------------

        articles = data.get("articles", []) or []

        total_results = data.get("totalResults", 0) or 0

        logging.info(
            "NewsAPI returned %d articles. "
            "Requested page size: %d. "
            "Page: %d. Topic: %s.",
            len(articles),
            NEWSAPI_PAGE_SIZE,
            page,
            topic,
        )

        # --------------------------------------------------
        # 7. Process each article
        # --------------------------------------------------

        for item in articles:

            # Ignore malformed entries, but do not discard
            # articles simply because their URLs are missing.
            if not isinstance(item, dict):
                continue

            # Get the article URL.
            original_url = item.get("url") or ""

            # Keep only valid URLs for clickable article links.
            # IMPORTANT: Do not skip the article if the URL
            # is invalid. The card can still be displayed.
            safe_url = (
                original_url
                if valid_http_url(original_url)
                else ""
            )

            # --------------------------------------------------
            # Get basic information from NewsAPI
            # --------------------------------------------------

            source_information = item.get("source") or {}

            if not isinstance(source_information, dict):
                source_information = {}

            title = (
                item.get("title")
                or "Title unavailable"
            )

            description = (
                item.get("description")
                or ""
            )

            api_content = (
                item.get("content")
                or ""
            )

            author = item.get("author") or "Unknown"

            image = item.get("urlToImage") or ""

            published_at = (
                item.get("publishedAt")
                or ""
            )

            source = (
                source_information.get("name")
                or "Unknown source"
            )

            # --------------------------------------------------
            # Prepare fallback summary
            # --------------------------------------------------

            summary = description or api_content

            # Remove NewsAPI's common truncation marker.
            if summary:
                summary = summary.replace("[+chars]", "").strip()

            # --------------------------------------------------
            # Attempt Newspaper3k extraction
            # --------------------------------------------------

            # Only attempt to download the article when its
            # URL is valid. Extraction failure must not remove
            # the original NewsAPI article from the results.
            extracted = extract_article_details(safe_url)

            # Prefer extracted information when available.
            # Otherwise, retain the NewsAPI information.
            title = extracted.get("title") or title

            summary = (
                extracted.get("summary")
                or summary
                or "No summary is available for this article."
            )

            author = extracted.get("author") or author

            image = extracted.get("image") or image

            # --------------------------------------------------
            # Build article dictionary for the HTML template
            # --------------------------------------------------

            article_data = {
                "title": title,
                "summary": summary,
                "url": safe_url,
                "image": image,
                "source": source,
                "author": author,
                "published_at": published_at,
                "category": topic.title(),
            }

            # Add this article even if it has no valid URL.
            displayed_articles.append(article_data)

        # --------------------------------------------------
        # 8. Log the final article count
        # --------------------------------------------------

        logging.info(
            "Prepared %d article cards for page %d.",
            len(displayed_articles),
            page,
        )

    except requests.exceptions.Timeout:
        error = (
            "The request to NewsAPI timed out. "
            "Please try again later."
        )

        logging.exception("NewsAPI request timed out.")

    except requests.exceptions.HTTPError as exception:
        error = (
            "NewsAPI returned an HTTP error. "
            "Please check your API key and API usage limits."
        )

        logging.exception(
            "NewsAPI HTTP error: %s",
            exception,
        )

    except requests.exceptions.RequestException as exception:
        error = (
            "Unable to connect to NewsAPI. "
            "Please check your internet connection."
        )

        logging.exception(
            "NewsAPI connection error: %s",
            exception,
        )

    except ValueError as exception:
        error = (
            "NewsAPI returned an invalid response. "
            "Please try again."
        )

        logging.exception(
            "Could not decode NewsAPI response: %s",
            exception,
        )

    except Exception as exception:
        error = (
            "An unexpected error occurred while retrieving news."
        )

        logging.exception(
            "Unexpected error in fetch_news(): %s",
            exception,
        )

    return displayed_articles, error, total_results


# ==========================================================
# MAIN ROUTE
# ==========================================================

@app.route("/", methods=["GET"])
def index():
    """
    Display the news homepage.

    Supports:
        - Category filtering
        - Keyword search
        - Pagination
        - Error messages
    """

    # Get search parameters from the URL.
    topic = request.args.get("topic", "general")

    query = request.args.get("query", "").strip()

    page = request.args.get("page", 1, type=int)

    # Handle an invalid page number.
    if page is None or page < 1:
        page = 1

    page = min(page, MAX_PAGE)

    # Validate the requested category.
    topic = (topic or "general").strip().lower()

    if topic not in ALLOWED_CATEGORIES:
        topic = "general"

    # Retrieve articles.
    articles, error, total_results = fetch_news(
        topic=topic,
        query=query,
        page=page,
    )

    # Calculate the number of pages using NewsAPI's
    # reported total results.
    if total_results > 0:
        total_pages = min(
            MAX_PAGE,
            math.ceil(total_results / NEWSAPI_PAGE_SIZE),
        )
    else:
        total_pages = 0

    # Render the homepage.
    return render_template(
        "index.html",
        articles=articles,
        error=error,
        topic=topic,
        query=query,
        page=page,
        total_pages=total_pages,
    )


# ==========================================================
# RUN APPLICATION
# ==========================================================

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False
    )