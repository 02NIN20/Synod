"""CSRF missing protection sample."""
from flask import Flask, request, session

app = Flask(__name__)


@app.route("/transfer", methods=["POST"])
def transfer_money():
    amount = request.form.get("amount")
    to_account = request.form.get("to_account")
    # No CSRF token validation
    execute_transfer(session["user_id"], to_account, amount)
    return "Transfer complete"


@app.route("/change_email", methods=["POST"])
def change_email():
    new_email = request.form.get("email")
    # No CSRF token validation
    update_user_email(session["user_id"], new_email)
    return "Email updated"


def execute_transfer(user_id, to_account, amount):
    pass


def update_user_email(user_id, email):
    pass
