"""XSS vulnerable sample."""
from flask import Flask, request, render_template_string

app = Flask(__name__)


@app.route("/greet")
def greet():
    name = request.args.get("name", "")
    template = f"<h1>Hello, {name}!</h1>"
    return render_template_string(template)


@app.route("/comment", methods=["POST"])
def comment():
    text = request.form.get("text", "")
    html = f"<div class='comment'>{text}</div>"
    return html


@app.route("/search")
def search():
    query = request.args.get("q", "")
    results_html = f"<p>Results for: {query}</p>"
    return results_html
