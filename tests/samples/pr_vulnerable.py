import os, sqlite3
from flask import Flask, request, render_template_string

app = Flask(__name__)
API_KEY = "sk-live-1234567890"

@app.route("/run")
def run_cmd():
    cmd = request.args.get("cmd")
    os.system(cmd)
    return "done"

@app.route("/search")
def search():
    user = request.args.get("user")
    conn = sqlite3.connect("db.sqlite")
    conn.execute(f"SELECT * FROM users WHERE name = '{user}'")
    return render_template_string(f"<h1>Hello {user}</h1>")

if __name__ == "__main__":
    app.run()
# trigger webhook synchronize
# second synchronize trigger
