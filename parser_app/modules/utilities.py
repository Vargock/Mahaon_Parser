import os
from urllib.parse import urlparse
import re
import sqlite3


def get_db_connection():
    conn = sqlite3.connect("products.db")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode=WAL;")  # Enable WAL mode for better concurrency
    return conn


def get_image_folder(url):
    path = urlparse(url).path.strip("/").split("/")
    if len(path) >= 3:
        product_type, product_maker, product = path[-3], path[-2], path[-1]
    else:
        product_type, product_maker, product = "unknown", "unknown", "unknown"
    folder = os.path.join("images", product_type, product_maker, product)
    return folder, product


def sanitize_filename(name):
    return re.sub(r"[^\w\-]", "_", name.strip())


def normalize_image_path(path):
    """
    Normalizes and sanitizes an image path to ensure it starts with 'static/images/'.

    - Converts backslashes to slashes.
    - Removes leading/trailing slashes.
    - Ensures the path begins with 'static/images/'.
    - Prevents path traversal (e.g., '..' segments).

    Args:
        path (str | None): The raw image path to normalize.

    Returns:
        str | None: A cleaned-up path or None if invalid.
    """
    if not path or not isinstance(path, str):
        return None

    # Strip whitespace
    path = path.strip().lstrip("/")

    # Prevent path traversal
    if ".." in path or path.startswith("../"):
        return None

    # Normalize duplicate segments like "static/static/images"
    path = path.replace("static/static/images", "static/images")

    # Ensure it starts with 'static/images/'
    if not path.startswith("static/images"):
        path = os.path.join("static/images", path).replace("\\", "/")

    return path
