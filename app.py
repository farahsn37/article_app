# from flask import Flask, render_template

# app = Flask(__name__)

# @app.route('/')
# def index():
#     articles = [
#         {'title': 'Article 1', 'content' : 'This is the content of Article 1.'},
#         {'title': 'Article 2', 'content' : 'This is the content of Article 2.'},
#         # add more article
#     ]
#     return render_template('index.html', articles=articles)

# if __name__ == '__main__':
#     app.run(debug=True)



from flask import Flask, render_template, abort, request

app = Flask(__name__)

articles = [
    {
        "id": 1,
        "title": "The Future of Artificial Intelligence",
        "category": "Technology",
        "author": "Alex Tan",
        "summary": "Discover how AI is changing the way we learn, work, and communicate.",
        "content": """
        Artificial intelligence is becoming an important part of modern life.
        It can help people analyse information, automate repetitive tasks,
        and discover new ways to solve problems.
        """
    },
    {
        "id": 2,
        "title": "Building Better Learning Habits",
        "category": "Education",
        "author": "Sarah Lee",
        "summary": "Explore practical ways to improve learning and manage your time.",
        "content": """
        Effective learning involves consistent practice, clear goals,
        and regular breaks. Breaking a large task into smaller steps
        can make studying more manageable.
        """
    },
    {
        "id": 3,
        "title": "Understanding Data Science",
        "category": "Technology",
        "author": "Daniel Wong",
        "summary": "Learn how data can help people make better decisions.",
        "content": """
        Data science combines programming, statistics, and domain knowledge
        to extract useful information from data. Organisations use these
        insights to understand trends and improve their decisions.
        """
    }
]


@app.route("/")
def home():
    search_query = request.args.get("q", "").strip().lower()

    filtered_articles = [
        article for article in articles
        if search_query in article["title"].lower()
        or search_query in article["summary"].lower()
        or search_query in article["category"].lower()
    ]

    return render_template(
        "index.html",
        articles=filtered_articles,
        search_query=search_query
    )


@app.route("/article/<int:article_id>")
def article_detail(article_id):
    article = next(
        (item for item in articles if item["id"] == article_id),
        None
    )

    if article is None:
        abort(404)

    return render_template("article.html", article=article)


if __name__ == "__main__":
    app.run(debug=True)
