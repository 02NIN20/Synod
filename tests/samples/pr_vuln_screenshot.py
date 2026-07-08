import os, sqlite3
from flask import Flask, request, render_template_string

app = Flask(__name__)
API_KEY = "sk-live-DEBUG-KEY"

@app.route("/exec")
def exec():
    cmd = request.args.get("cmd")
    os.system(cmd)
    return "done"

@app.route("/query")
def query():
    user = request.args.get("user")
    conn = sqlite3.connect("app.db")
    conn.execute(f"SELECT * FROM users WHERE name = '{user}'")
    return render_template_string(f"<p>{user}</p>")
