from .utilities import get_db_connection
import json


def get_session_status(session_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT status, product_urls, progress 
        FROM parse_sessions 
        WHERE session_id = ?
        """,
        (session_id,),
    )
    result = cursor.fetchone()
    conn.close()
    if result:
        status, product_urls, progress = result
        product_urls = json.loads(product_urls) if product_urls else []
        return status, product_urls, progress
    return "in_progress", [], "collecting_urls"


def get_logs(session_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT log_message FROM parse_logs WHERE session_id = ? ORDER BY timestamp",
        (session_id,),
    )
    logs = [row[0] for row in cursor.fetchall()]
    conn.close()
    return logs


def get_categories_from_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT category FROM products ORDER BY category")
    categories = [row[0] for row in cursor.fetchall()]
    conn.close()
    return categories


def get_existing_image_paths(url):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT image_path FROM products WHERE url = ?", (url,))
    main_image_path = cursor.fetchone()
    main_image_path = main_image_path[0] if main_image_path else None

    cursor.execute(
        """
        SELECT article_number, variant_name, image_path 
        FROM variants 
        WHERE product_id = (SELECT id FROM products WHERE url = ?)
        """,
        (url,),
    )
    variant_image_paths = {f"{row[0]}_{row[1]}": row[2] for row in cursor.fetchall()}

    conn.close()
    return main_image_path, variant_image_paths
