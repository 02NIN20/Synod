"""Intentionally vulnerable sample for testing Synod agents."""

import os
import sqlite3
import subprocess

# Hardcoded secret (security)
API_KEY = "sk-1234567890abcdef"
DB_PASSWORD = "supersecret"


# SQL injection (security)
def query_db(user_input: str) -> list:
    conn = sqlite3.connect("test.db")
    cursor = conn.cursor()
    query = f"SELECT * FROM users WHERE name = '{user_input}'"
    cursor.execute(query)
    return cursor.fetchall()


# Mutable default argument (quality)
def process(data: list = []) -> list:
    data.append("processed")
    return data


# Command injection (security)
def run_command(cmd: str) -> None:
    os.system(cmd)


# subprocess with shell=True (security)
def run_package_check(package: str) -> None:
    subprocess.run(f"dpkg -l {package}", shell=True)


# Nested loops complexity (quality)
def nested_loops(n: int) -> list:
    result = []
    for i in range(n):
        for j in range(n):
            for k in range(n):
                result.append(i * j * k)
    return result


# Dead code (quality)
def unused_function() -> str:
    return "never called"


# Insecure eval (security)
def evaluate_expression(expr: str):
    return eval(expr)
