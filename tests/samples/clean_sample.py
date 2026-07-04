"""Clean sample: no security issues, no quality issues. Expected: 0 findings."""

import os
import sqlite3
from dataclasses import dataclass


@dataclass
class User:
    name: str
    email: str


class UserRepository:
    """Handles user persistence."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def find_by_name(self, name: str) -> list[tuple]:
        """Fetch users by name using a parameterized query."""
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE name = ?", (name,))
            return cursor.fetchall()

    def create(self, user: User) -> None:
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (name, email) VALUES (?, ?)",
                (user.name, user.email),
            )
            conn.commit()


def get_api_key() -> str:
    """Reads API key from environment, never hardcoded."""
    key = os.environ.get("API_KEY")
    if not key:
        raise RuntimeError("API_KEY environment variable is not set")
    return key


def sum_positive(numbers: list[int]) -> int:
    """Sum only the positive numbers in a list."""
    return sum(n for n in numbers if n > 0)


def format_greeting(name: str) -> str:
    """Return a simple greeting message."""
    return f"Hello, {name}!"
