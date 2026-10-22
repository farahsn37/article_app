
import logging
import os
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from flask import Flask, abort, render_template, request
from newspaper import Article
from newspaper.article import ArticleException
from math import ceil


# --------------------------------------------------
# 1. Application configuration
# --------------------------------------------------

load_dotenv()

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "").strip()
NEWSAPI_COUNTRY = os.getenv("NEWSAPI_COUNTRY", "us").strip().lower()
NEWSAPI_PAGE_SIZE =10
MAX_PAGE = 100

try:
    configured_size = int(os.getenv("NEWSAPI_PAGE_SIZE", "10"))
    NEWSAPI_PAGE_SIZE = max(1, min(configured_size, 100))
except (TypeError, ValueError):
    logging.warning("Invalid NEWSAPI_PAGE_SIZE; using 10.")

NEWSAPI_URL = "https://newsapi.org/v2/top-headlines"

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
# 2. Utility functions
# --------------------------------------------------

def truncate_text(text, limit=220):
    """Return a shortened preview without cutting a word."""
    try:
        text = " ".join((text or "").split())

        if len(text) <= limit:
            return text

        shortened = text[:limit].rsplit(" ", 1)[0]
        return shortened.rstrip(".,;:") + "..."

    except (AttributeError, TypeError):
        logging.exception("Could not truncate article text.")
        return ""


def valid_http_url(url):
    """Allow only absolute HTTP/HTTPS URLs."""
    try:
        if not isinstance(url, str):
            return False

        parsed = urlparse(url.strip())

        return (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and not any(char.isspace() for char in url)
        )

    except (TypeError, ValueError):
        logging.exception("Could not validate URL.")
        return False


def safe_image_url(url):
    """Return an image URL only when it uses HTTP or HTTPS."""
    try:
        return url.strip() if valid_http_url(url) else ""

    except (AttributeError, TypeError):
        logging.exception("Could not validate image URL.")
        return ""


# --------------------------------------------------
# 3. Fetch articles from NewsAPI
# --------------------------------------------------

def fetch_news(category="general", query="", page=1):
    """
    Fetch one page of news from NewsAPI, extract accessible
    articles using Newspaper3k, and skip inaccessible articles.

    Returns:
        articles: List of extracted article dictionaries.
        error: Error message or None.
        total_results: Total number of raw results from NewsAPI.
    """

    # 1. Check API configuration
    if not NEWSAPI_KEY:
        logging.error("NEWSAPI_KEY is missing from the .env file.")
        return (
            [],
            "NewsAPI is not configured. Check your .env file.",
            0,
        )

    # 2. Validate input parameters
    try:
        page = max(1, min(int(page), MAX_PAGE))
    except (TypeError, ValueError):
        page = 1

    try:
        category = (category or "general").strip().lower()
        query = (query or "").strip()[:100]

        if category not in ALLOWED_CATEGORIES:
            category = "general"

    except (AttributeError, TypeError):
        logging.exception("Invalid news search parameters.")
        category = "general"
        query = ""

    # 3. Prepare NewsAPI request
    params = {
        "country": NEWSAPI_COUNTRY,
        "category": category,
        "page": page,
        "pageSize": NEWSAPI_PAGE_SIZE,
    }

    if query:
        params["q"] = query

    headers = {
        "X-Api-Key": NEWSAPI_KEY,
        "Accept": "application/json",
    }

    # 4. Request articles from NewsAPI
    try:
        response = requests.get(
            NEWSAPI_URL,
            params=params,
            headers=headers,
            timeout=(3.05, 12),
        )

        response.raise_for_status()

        try:
            payload = response.json()
        except ValueError:
            logging.error("NewsAPI returned invalid JSON.")
            return (
                [],
                "The news service returned an invalid response.",
                0,
            )

        if not isinstance(payload, dict):
            logging.error("Unexpected NewsAPI response format.")
            return (
                [],
                "The news service returned unexpected data.",
                0,
            )

        if payload.get("status") != "ok":
            error_code = payload.get("code", "unknown")
            logging.error("NewsAPI error code: %s", error_code)

            if error_code == "apiKeyInvalid":
                message = "The NewsAPI key is invalid."
            elif error_code == "apiKeyExhausted":
                message = "The NewsAPI request quota has been exhausted."
            elif error_code == "rateLimited":
                message = "Too many requests. Please try again later."
            else:
                message = "The news service could not provide articles."

            return [], message, 0

        # 5. Read total results and current page articles
        try:
            total_results = max(
                0,
                int(payload.get("totalResults", 0)),
            )
        except (TypeError, ValueError):
            total_results = 0

        raw_articles = payload.get("articles", [])

        if not isinstance(raw_articles, list):
            logging.error("NewsAPI articles field is not a list.")
            return (
                [],
                "The news service returned unexpected article data.",
                0,
            )

    except requests.exceptions.Timeout:
        logging.warning("NewsAPI request timed out.")
        return (
            [],
            "The news service took too long to respond.",
            0,
        )

    except requests.exceptions.HTTPError as exc:
        status_code = (
            exc.response.status_code
            if exc.response is not None
            else None
        )

        logging.error("NewsAPI HTTP error: %s", status_code)

        if status_code == 401:
            message = "NewsAPI rejected the API key. Check your .env file."
        elif status_code == 429:
            message = "The NewsAPI request limit has been reached."
        elif status_code == 400:
            message = "The news request contains invalid parameters."
        else:
            message = "The news service is temporarily unavailable."

        return [], message, 0

    except requests.exceptions.RequestException:
        logging.exception("Could not connect to NewsAPI.")
        return (
            [],
            "Could not connect to the news service.",
            0,
        )

    except Exception:
        logging.exception("Unexpected error while requesting NewsAPI.")
        return (
            [],
            "An unexpected news retrieval error occurred.",
            0,
        )

    # 6. Extract individual publisher articles
    displayed_articles = []
    seen_urls = set()

    for item in raw_articles:
        try:
            if not isinstance(item, dict):
                continue

            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip()
            description = (item.get("description") or "").strip()

            # Skip removed or incomplete records
            if not title or title.lower() == "[removed]":
                continue

            if description.lower() == "[removed]":
                continue

            if not valid_http_url(url):
                continue

            if url in seen_urls:
                continue

            seen_urls.add(url)

            # 7. Download and parse the publisher webpage
            try:
                extracted = Article(
                    url,
                    language="en",
                    request_timeout=10,
                )

                extracted.download()
                extracted.parse()

            except ArticleException as exc:
                error_message = str(exc).lower()

                if "403" in error_message or "forbidden" in error_message:
                    logging.info(
                        "Skipping publisher-blocked article: %s",
                        url,
                    )
                else:
                    logging.info(
                        "Skipping article that could not be extracted: %s",
                        url,
                    )

                continue

            except requests.exceptions.HTTPError as exc:
                status_code = (
                    exc.response.status_code
                    if exc.response is not None
                    else None
                )

                if status_code == 403:
                    logging.info(
                        "Skipping forbidden article: %s",
                        url,
                    )
                else:
                    logging.info(
                        "Skipping article with HTTP error %s: %s",
                        status_code,
                        url,
                    )

                continue

            except requests.exceptions.RequestException:
                logging.info(
                    "Skipping article because of a network error: %s",
                    url,
                )
                continue

            except Exception:
                logging.exception(
                    "Unexpected extraction error for article: %s",
                    url,
                )
                continue

            # 8. Validate extracted content
            content = (extracted.text or "").strip()

            # Do not display empty or very short articles
            if len(content) < 80:
                logging.info(
                    "Skipping article with insufficient content: %s",
                    url,
                )
                continue

            # 9. Resolve author and source information
            source_data = item.get("source") or {}

            if not isinstance(source_data, dict):
                source_data = {}

            extracted_authors = extracted.authors or []
            api_author = item.get("author") or ""

            if isinstance(api_author, str):
                api_author = api_author.strip()
            else:
                api_author = ""

            if extracted_authors:
                author = ", ".join(extracted_authors)
            else:
                author = api_author or source_data.get("name") or "Unknown author"

            source_name = source_data.get("name") or "News source"
            published_at = item.get("publishedAt") or ""

            # 10. Resolve article image
            image_url = safe_image_url(
                extracted.top_image or item.get("urlToImage") or ""
            )

            # 11. Keep the existing content structure and add image
            displayed_articles.append({
                "id": len(displayed_articles) + 1,
                "title": extracted.title or title,
                "category": category.title(),
                "author": author,
                "summary": description or truncate_text(content, 180),
                "image": image_url,
                "content": truncate_text(content, 600),
                "preview": truncate_text(content, 220),
                "url": url,
                "source": source_name,
                "published_at": published_at,
            })

        except Exception:
            logging.exception(
                "Skipping invalid article record from NewsAPI."
            )
            continue

    # 12. Return this page's accessible articles and API result count
    logging.info(
        "NewsAPI page %s: %s accessible articles out of %s raw results.",
        page,
        len(displayed_articles),
        len(raw_articles),
    )

    return displayed_articles, None, total_results

# --------------------------------------------------
# 4. Homepage
# --------------------------------------------------


@app.route("/")
def home():
    try:
        category = request.args.get("category", "general").lower().strip()
        query = request.args.get("q", "").strip()[:100]

        try:
            page = int(request.args.get("page", 1))
        except (TypeError, ValueError):
            page = 1

        page = max(1, min(page, MAX_PAGE))

        if category not in ALLOWED_CATEGORIES:
            category = "general"

        articles, error, total_results = fetch_news(
            category=category,
            query=query,
            page=page,
        )

        total_pages = min(
            MAX_PAGE,
            ceil(total_results / NEWSAPI_PAGE_SIZE),
        )

        # Keep the displayed page within the available range.
        # Re-fetch if a user requests a page beyond the result count.
        if total_pages > 0 and page > total_pages:
            page = total_pages
            articles, error, total_results = fetch_news(
                category=category,
                query=query,
                page=page,
            )
            total_pages = min(
                MAX_PAGE,
                ceil(total_results / NEWSAPI_PAGE_SIZE),
            )

        return render_template(
            "index.html",
            articles=articles,
            category=category,
            search_query=query,
            categories=sorted(ALLOWED_CATEGORIES),
            error=error,
            page=page,
            total_pages=total_pages,
            total_results=total_results,
            has_previous=page > 1,
            has_next=page < total_pages and page < MAX_PAGE,
        )

    except Exception:
        logging.exception("Homepage failed.")
        return render_template(
            "index.html",
            articles=[],
            category="general",
            search_query="",
            categories=sorted(ALLOWED_CATEGORIES),
            error="The page could not load news. Please try again.",
            page=1,
            total_pages=0,
            total_results=0,
            has_previous=False,
            has_next=False,
        ), 500


# --------------------------------------------------
# 5. Article details
# --------------------------------------------------


@app.route("/article/<int:article_id>")
def article_detail(article_id):
    try:
        category = request.args.get("category", "general").lower().strip()
        query = request.args.get("q", "").strip()[:100]

        try:
            page = max(
                1,
                min(int(request.args.get("page", 1)), MAX_PAGE),
            )
        except (TypeError, ValueError):
            page = 1

        if category not in ALLOWED_CATEGORIES:
            category = "general"

        articles, error, _ = fetch_news(
            category=category,
            query=query,
            page=page,
        )

        if error:
            abort(503, description=error)

        article = next(
            (item for item in articles if item["id"] == article_id),
            None,
        )

        if article is None:
            abort(404)

        return render_template(
            "article.html",
            article=article,
            page=page,
            category=category,
            search_query=query,
        )

    except Exception as exc:
        from werkzeug.exceptions import HTTPException

        if isinstance(exc, HTTPException):
            raise

        logging.exception("Article detail page failed.")
        abort(500, description="Unable to display this article.")


# --------------------------------------------------
# 6. Friendly error pages
# --------------------------------------------------

@app.errorhandler(404)
def page_not_found(error):
    try:
        return render_template(
            "error.html",
            message="This article could not be found.",
        ), 404
    except Exception:
        logging.exception("Could not render 404 page.")
        return "Page not found.", 404


@app.errorhandler(503)
def service_unavailable(error):
    try:
        return render_template(
            "error.html",
            message=getattr(error, "description", "News service unavailable."),
        ), 503
    except Exception:
        logging.exception("Could not render 503 page.")
        return "News service unavailable.", 503


@app.errorhandler(500)
def internal_error(error):
    logging.error("A server error occurred.")
    try:
        return render_template(
            "error.html",
            message="Something went wrong. Please try again.",
        ), 500
    except Exception:
        logging.exception("Could not render 500 page.")
        return "Internal server error.", 500


# --------------------------------------------------
# 7. Run locally
# --------------------------------------------------

if __name__ == "__main__":
    try:
        app.run(debug=False)
    except Exception:
        logging.exception("Flask server failed to start.")

