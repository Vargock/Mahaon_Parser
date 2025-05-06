import sqlite3
from datetime import datetime
import json

# Import modules
from .utilities import normalize_image_path, get_db_connection
from .classes import Product, Variant
from .logger import log_message


def create_db():
    """
    Initializes the application's SQLite database.

    This function connects to the database (creating it if it does not exist),
    creates the necessary tables for product data, variants, parsing sessions,
    and logs. It also creates relevant indexes to optimize query performance.

    If the database already exists, tables and indexes are created only if they don't exist.
    After creating the schema, it applies    additional migrations via `migrate_db()`.
    """

    # Connect to the database and enable foreign key support
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    # --- Create the migration_history table to track migrations ---
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS migration_history (
            migration_id TEXT PRIMARY KEY,
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    # --- Create 'products' table ---
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY,
            category TEXT,
            title TEXT,
            price TEXT,
            sostav TEXT,
            ves_motka TEXT,
            dlina_motka TEXT,
            ves_upakovki TEXT,
            image_path TEXT,
            url TEXT UNIQUE,
            last_updated DATETIME,
            is_complete BOOLEAN DEFAULT 0
        )
        """
    )

    # --- Create 'variants' table ---
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS variants (
            id INTEGER PRIMARY KEY,
            product_id INTEGER,
            article_number TEXT,
            variant_name TEXT,
            is_available BOOLEAN,
            image_path TEXT,
            image_url TEXT,
            last_updated DATETIME,
            is_complete BOOLEAN DEFAULT 0,
            FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE,
            UNIQUE (product_id, article_number, variant_name)
        )
        """
    )

    # --- Create 'parse_sessions' table ---
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS parse_sessions (
            session_id TEXT PRIMARY KEY,
            status TEXT,
            created_at DATETIME,
            updated_at DATETIME,
            product_urls TEXT,
            progress TEXT,
            category_name TEXT
        )
        """
    )

    # --- Create 'parse_logs' table ---
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS parse_logs (
            id INTEGER PRIMARY KEY,
            session_id TEXT,
            log_message TEXT,
            timestamp DATETIME,
            FOREIGN KEY (session_id) REFERENCES parse_sessions (session_id)
        )
        """
    )

    # --- Create indexes for performance ---
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_url ON products (url)")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_products_category ON products (category)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_variants_product_id ON variants (product_id, article_number)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_parse_logs_session_id ON parse_logs (session_id)"
    )

    # Commit changes and close the connection
    conn.commit()
    conn.close()

    # Apply migrations for existing databases (if needed)

    # migrate_db()


def migrate_db():
    """Apply schema migrations to existing database."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get the list of applied migrations
    cursor.execute("SELECT migration_id FROM migration_history")
    applied_migrations = {row[0] for row in cursor.fetchall()}
    # Define a list of migrations that we want to apply

    migrations = [
        {
            "migration_id": "2025_05_01_add_is_complete_to_products",
            "alter_table": "products",
            "add_column": ("is_complete", "BOOLEAN", 1),
        },
        {
            "migration_id": "2025_05_02_add_is_complete_to_variants",
            "alter_table": "variants",
            "add_column": ("is_complete", "BOOLEAN", 1),
        },
        {
            "migration_id": "2025_05_03_add_product_urls_to_parse_sessions",
            "alter_table": "parse_sessions",
            "add_column": ("product_urls", "TEXT", None),
        },
        {
            "migration_id": "2025_05_04_add_progress_to_parse_sessions",
            "alter_table": "parse_sessions",
            "add_column": ("progress", "TEXT", None),
        },
        {
            "migration_id": "2025_05_05_add_category_name_to_parse_sessions",
            "alter_table": "parse_sessions",
            "add_column": ("category_name", "TEXT", None),
        },
    ]

    # Loop over the migrations and apply them if they haven't been applied
    for migration in migrations:
        if migration["migration_id"] not in applied_migrations:
            print(f"Applying migration: {migration['migration_id']}")

            if "alter_table" in migration:
                table = migration["alter_table"]
                column, column_type, default_value = migration["add_column"]
                default_value_clause = (
                    f"DEFAULT {default_value}" if default_value is not None else ""
                )
                cursor.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {column_type} {default_value_clause}"
                )

                # After adding the column, set default value for existing rows
                if default_value is not None:
                    cursor.execute(f"UPDATE {table} SET {column} = {default_value}")

            elif "sql" in migration:
                for query in migration["sql"]:
                    cursor.execute(query)

            # Mark the migration as applied
            cursor.execute(
                "INSERT INTO migration_history (migration_id) VALUES (?)",
                (migration["migration_id"],),
            )
            conn.commit()

    conn.close()


def save_to_db(
    product: Product,
    variants: list[Variant],
    session_id: str,
    cancel_flags: dict[str, bool],
) -> bool:
    """
    Saves product and its variants to the SQLITE Database.

    Args:
        product (Product): The main product to be saved.
        variants (List[Variant]): List of product variants (e.g., color options).
        session_id (str): The current parsing session ID for logging.
        cancel_flags (Dict[str, bool]): Dict of session_id -> bool to cancel operation if needed.

    Returns:
        bool: True if saving was successful, False otherwise.
    """

    # 1. Check if the operation was canceled before proceeding
    if cancel_flags.get(session_id, False):
        log_message(
            session_id,
            "⚠️ Парсинг отменен, данные не сохраняются | Step #1 | save_to_db(...) found cancel_flag",
            level="warning",
        )
        return False

    # 2. Connect to the database
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    # 3. Convert product to dictionary and normalize image path
    product_data = product.to_dict()
    product_data["image_path"] = normalize_image_path(product_data["image_path"])

    # 4. Validate product image path (can be None)
    if not product_data["image_path"]:
        log_message(
            session_id,
            f"❌ Недействительный путь изображения: {product_data['image_path']} | Step #4 | save_to_db(...) could not validate product_data['image_path']",
            level="error",
        )
        product_data["image_path"] = None

    # 5. Ensure the product has a valid title before saving
    if not product_data["title"] or product_data["title"] == "Не найдено":
        log_message(
            session_id,
            f"❌ Неверные данные продукта: {product_data['url']}  | Step #5 | save_to_db(...) could not validate product_data['title']",
            level="error",
        )
        conn.close()
        return False

    # 6. Try to insert or update product in the database
    try:
        cursor.execute(
            """
            INSERT INTO products (
                category, title, price, sostav, ves_motka, dlina_motka,
                ves_upakovki, image_path, url, last_updated, is_complete
            ) VALUES (
                :category, :title, :price, :sostav, :ves_motka, :dlina_motka,
                :ves_upakovki, :image_path, :url, :last_updated, 1
            )
            ON CONFLICT(url) DO UPDATE SET
                category = excluded.category,
                title = excluded.title,
                price = excluded.price,
                sostav = excluded.sostav,
                ves_motka = excluded.ves_motka,
                dlina_motka = excluded.dlina_motka,
                ves_upakovki = excluded.ves_upakovki,
                image_path = excluded.image_path,
                last_updated = excluded.last_updated,
                is_complete = 1;
            """,
            product_data,
        )

        conn.commit()
        log_message(
            session_id,
            f"✅ Успешно сохранено: {product_data} | save_to_db(...) [product_data]",
            level="info",
        )

    except sqlite3.Error as e:
        log_message(
            session_id,
            f"❌ Ошибка при сохранении продукта {product_data['url']}: {e} | Step #6 | save_to_db(...) could not save product_data into products.db",
            level="error",
        )
        conn.rollback()
        conn.close()
        return False

    # 7. Retrieve product_id for use in saving variants
    cursor.execute("SELECT id FROM products WHERE url = ?", (product.url,))
    result = cursor.fetchone()
    if result is None:
        log_message(
            session_id,
            f"❌ Ошибка: Продукт с URL {product.url} не был сохранен в базе данных | Step #7 | save_to_db(...) could not retrieve product_url from db",
            level="error",
        )
        conn.close()
        return False

    product_id = result[0]

    # 8. Save variants for the product
    for variant in variants:
        # Check if the operation was canceled inside the loop
        if cancel_flags.get(session_id, False):
            log_message(
                session_id,
                "⚠️ Парсинг отменен, прекращение сохранения вариантов | Step #8.1 | save_to_db(...) found cancel_flag,",
                level="warning",
            )
            break

        # Process each variant
        variant_data = variant.to_dict()
        variant_data["image_path"] = normalize_image_path(variant_data["image_path"])

        # Validate variant image path
        if variant_data["image_path"] and not variant_data["image_path"].startswith(
            "static/images"
        ):
            log_message(
                session_id,
                f"❌ Недействительный путь изображения варианта {variant_data['variant_name']}[{variant_data['article_number']}]: {variant_data['image_path']} | Step #8.2 | save_to_db(...) could not validate variand_data['image_path']",
                level="error",
            )
            variant_data["image_path"] = None

        # Try to insert or update variant in the database
        try:
            cursor.execute(
                """
                INSERT INTO variants (
                    product_id, article_number, variant_name, is_available,
                    image_path, image_url, last_updated, is_complete
                ) VALUES (
                    :product_id, :article_number, :variant_name, :is_available,
                    :image_path, :image_url, :last_updated, 1
                )
                ON CONFLICT(product_id, article_number, variant_name) DO UPDATE SET
                    is_available = excluded.is_available,
                    image_path = excluded.image_path,
                    image_url = excluded.image_url,
                    last_updated = excluded.last_updated,
                    is_complete = 1;
                """,
                variant_data,
            )
        except sqlite3.Error as e:
            log_message(
                session_id,
                f"❌ Ошибка при сохранении варианта {variant_data["variant_name"], variant_data["article_number"]} для продукта {product_id}: {e} | Step #8.3 | save_to_db(...) failed to save variand_data",
                level="error",
            )
            conn.rollback()
            continue  # Move to the next variant if one fails

    # Commit changes and close the connection
    conn.commit()
    conn.close()
    return True


def cleanup_incomplete(session_id):
    """
    Deletes incomplete products and their related variants from the database.

    Args:
        session_id (str): The session ID for logging purposes.
    """

    # Connect to the database
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    # Delete products with is_complete = 0
    # Due to the ON DELETE CASCADE in the foreign key, related variants are also deleted automatically.
    cursor.execute("DELETE FROM products WHERE is_complete = 0")

    # Commit changes and close the connection
    conn.commit()
    conn.close()

    # Log cleanup completion
    deleted_count = cursor.rowcount
    log_message(
        session_id,
        f"🧹 Очищено {deleted_count} незавершенных продуктов | cleanup_incomplete(...)",
        level="info",
    )


def update_session_status(
    session_id, status, product_urls=None, progress=None, category_name=None
):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT OR REPLACE INTO parse_sessions (session_id, status, created_at, updated_at, product_urls, progress, category_name)
        VALUES (?, ?, COALESCE((SELECT created_at FROM parse_sessions WHERE session_id = ?), ?), ?, ?, ?, ?)
        """,
        (
            session_id,
            status,
            session_id,
            datetime.now().isoformat(" ", "minutes"),
            datetime.now().isoformat(" ", "minutes"),
            json.dumps(product_urls) if product_urls else None,
            progress,
            category_name,
        ),
    )
    conn.commit()
    conn.close()
