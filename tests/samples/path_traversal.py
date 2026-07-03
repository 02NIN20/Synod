"""Path traversal vulnerable sample."""
import os


def read_file(filename: str) -> str:
    path = os.path.join("/var/data/uploads", filename)
    with open(path, "r") as f:
        return f.read()


def delete_file(filename: str) -> None:
    path = "/var/data/uploads/" + filename
    os.remove(path)


def serve_static(filepath: str) -> bytes:
    full_path = f"./static/{filepath}"
    with open(full_path, "rb") as f:
        return f.read()
