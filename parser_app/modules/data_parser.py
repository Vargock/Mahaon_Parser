"""Module responsible for parsing fetched web data from Mahaon website

This module coordinates and executes parsing process, fetches data by utilising .data_fetcher module,
extracts data by using .data_extractor module, and saves it all to database by using .db_write. It handles parsing of single products, specific categories,
or all categories, ensuring data is structured and saved to the database.
"""

# Standard library imports
# Imports for type hints, HTTP request error handling, SQLite errors, thread synchronization, delays, and stack traces.
from typing import Optional, Dict, List, Union
from requests.exceptions import RequestException
from sqlite3 import Error as SQLiteError
import threading
import time
import traceback

# Local imports
# Imports logging, database writing functions, and data fetching utilities from other modules in the app.
from .logger import log_message
from .db_write import update_session_status, save_to_db, cleanup_incomplete
from .data_fetcher import fetch_categories, fetch_catalog_page, fetch_product_page

cancel_lock = threading.Lock()
# A threading lock to synchronize access to the cancel_flags dictionary, ensuring thread-safe cancellation checks.


def parse_catalog(
    catalog_url: str | None = None,
    category: str | None = None,
    max_pages: int | None = None,
    max_products: int | None = None,
    session_id: str | None = None,
    url: str | None = None,
    cancel_flags: dict[str, bool] | None = None,
    static_folder: str | None = None,
) -> dict[str, bool | int | str]:
    """Parse product data from a URL, category, or all categories.

    This function orchestrates the parsing process by determining whether to parse
    a single product, a specific category, or all categories. It fetches product URLs,
    processes them, and saves the results to the database. If more than 5 products are
    found, it pauses for user confirmation.

    Args:
        catalog_url: URL of a catalog page to parse (optional).
        category: Name of the category to assign to parsed products (optional).
        max_pages: Maximum number of catalog pages to parse (optional).
        max_products: Maximum number of products to parse (optional).
        session_id: Unique identifier for the parsing session (optional).
        url: Specific product or collection URL to parse (optional).
        cancel_flags: Dictionary tracking cancellation status for sessions (optional).
        static_folder: Path to the static folder for saving images (optional).

    Returns:
        dict: A dictionary with keys:
            - "success" (bool): Whether parsing completed successfully.
            - "products_processed" (int): Number of products parsed.
            - "message" (str): Parsing result message.

    Raises:
        ValueError: If required inputs are invalid.
        Exception: If an error occurs during parsing, it is logged and the session
            status is updated to 'error'.
    """
    # This function is the main entry point for parsing. It decides whether to parse a single product (if 'url' is provided), a category (if 'catalog_url' is provided), or all categories (if neither is provided).
    # It coordinates fetching URLs, parsing products, and saving to the database.

    # Input validation
    # Validates required inputs to prevent runtime errors. Ensures session_id is a non-empty string, and url/catalog_url are strings if provided.
    if not session_id or not isinstance(session_id, str):
        raise ValueError("session_id must be a non-empty string")
    if url and not isinstance(url, str):
        raise ValueError("url must be a string")
    if catalog_url and not isinstance(catalog_url, str):
        raise ValueError("catalog_url must be a string")
    if cancel_flags is None:
        raise ValueError("cancel_flags dictionary is required")

    # Logs the start of parsing with input details for debugging. Updates the session status in the database to 'in_progress' to track the parsing state.
    log_message(
        session_id,
        f"Starting parsing: URL={url}, Category={category}, Catalog={catalog_url}, "
        f"Max Pages={max_pages}, Max Products={max_products}",
        level="debug",
    )
    # Updates the session status in the database to 'in_progress' to track the parsing state.
    update_session_status(session_id, "in_progress", progress="collecting_urls")

    # Initializes a result dictionary to track parsing outcome: success status, number of products processed, and a summary message.
    result = {"success": False, "products_processed": 0, "message": ""}

    # Checks if the parsing session was canceled (via cancel_flags). If so, logs a warning and returns early with a cancellation message.
    with cancel_lock:
        if cancel_flags.get(session_id, False):
            log_message(session_id, "Parsing canceled at start", level="warning")
            result["message"] = "Parsing canceled"
            return result

    try:
        # Single product parsing branch: processes a single product URL.
        if url:
            log_message(session_id, f"Parsing single product: {url}", level="debug")
            try:
                # Fetches and parses the product page using fetch_product_page from data_fetcher.py
                # Assigns a default category if none provided.
                product = fetch_product_page(
                    url, category or "Unknown", session_id, cancel_flags, static_folder
                )

                # If fetch_product_page returns None (e.g., due to invalid URL or parsing failure), logs an error and returns early.
                if product is None:
                    log_message(
                        session_id,
                        f"Failed to fetch or parse product {url}: returned None",
                        level="error",
                    )
                    result["message"] = f"Failed to parse product {url}"
                    return result

                # Saves the product and its variants to the database using save_to_db. Logs success and updates result if successful.
                if save_to_db(product, product.variants, session_id, cancel_flags):
                    log_message(
                        session_id,
                        f"Successfully saved product: {product.title}",
                        level="info",
                    )
                    result["success"] = True
                    result["products_processed"] = 1
                    result["message"] = f"Successfully parsed and saved product {url}"
                else:  # If save_to_db fails (e.g., due to database issues), logs an error and sets the result message.
                    log_message(
                        session_id,
                        f"Error saving product {url}: check database logs",
                        level="error",
                    )
                    result["message"] = f"Error saving product {url}"
            # Handles HTTP-related errors (e.g., connection timeout) during product fetching.
            except RequestException as e:
                log_message(
                    session_id,
                    f"Network error processing product {url}: {e}",
                    level="error",
                )
                result["message"] = f"Network error: {e}"
            # Handles database errors (e.g., schema issues) during product saving.
            except SQLiteError as e:
                log_message(
                    session_id,
                    f"Database error processing product {url}: {e}",
                    level="error",
                )
                result["message"] = f"Database error: {e}"

        # Category parsing branch: processes a single category's product URLs.
        elif catalog_url:
            log_message(
                session_id, f"Parsing category catalog: {catalog_url}", level="debug"
            )

            # Fetches product URLs from the category page using fetch_catalog_page, respecting max_pages and max_products limits.
            product_urls = fetch_catalog_page(
                catalog_url, category, max_pages, max_products, session_id, cancel_flags
            )
            log_message(
                session_id,
                f"Found {len(product_urls)} product URLs in catalog",
                level="info",
            )

            # If more than 5 products are found, pauses parsing, updates session status to 'awaiting_confirmation', and returns early to wait for user approval.
            if len(product_urls) > 5:
                update_session_status(
                    session_id,
                    "awaiting_confirmation",
                    product_urls,
                    "awaiting_confirmation",
                )
                log_message(
                    session_id,
                    f"Found {len(product_urls)} products, awaiting confirmation",
                    level="warning",
                )
                result["message"] = (
                    f"Paused for confirmation: {len(product_urls)} products found"
                )
                return result
            # Processes the fetched product URLs using parse_product_urls, which handles fetching and saving individual products.
            processed = parse_product_urls(
                product_urls, category, session_id, cancel_flags, static_folder
            )

            # Updates the result with the outcome from parse_product_urls (success, count, and message).
            result["success"] = processed["success"]
            result["products_processed"] = processed["products_processed"]
            result["message"] = processed["message"]

        # All categories parsing branch: processes all categories on the website.
        else:
            log_message(session_id, "Parsing all categories", level="debug")
            # Fetches all category URLs from the website using fetch_categories.
            categories = fetch_categories()

            log_message(
                session_id,
                f"Found {len(categories)} categories to parse",
                level="info",
            )

            # Tracks the total number of products processed across all categories.
            total_processed = 0

            for cat in categories:
                with cancel_lock:
                    # Checks for cancellation before processing each category.
                    if cancel_flags.get(session_id, False):
                        log_message(
                            session_id,
                            "Parsing canceled, stopping category parsing",
                            level="warning",
                        )
                        result["message"] = (
                            "Parsing canceled during category processing"
                        )
                        return result

                # Stops if the maximum number of products has been reached.
                if max_products and total_processed >= max_products:
                    log_message(
                        session_id,
                        f"Reached product limit ({max_products})",
                        level="debug",
                    )
                    break

                # Fetches product URLs for the current category, adjusting max_products to respect the overall limit.
                cat_urls = fetch_catalog_page(
                    cat["url"],
                    cat["name"],
                    max_pages,
                    max_products - total_processed,
                    session_id,
                    cancel_flags,
                )
                log_message(
                    session_id,
                    f"Found {len(cat_urls)} URLs in category {cat['name']}",
                    level="debug",
                )

                for url in cat_urls:
                    # Processes each product URL individually, passing it as a tuple with the category name.
                    processed = parse_product_urls(
                        [(url, cat["name"])],
                        cat["name"],
                        session_id,
                        cancel_flags,
                        static_folder,
                    )

                    # Updates the total count and logs success for each product.
                    total_processed += processed["products_processed"]

                    # Updates the total count and logs success for each product.
                    if processed["success"]:
                        log_message(
                            session_id,
                            f"Successfully processed product {url} in category {cat['name']}",
                            level="info",
                        )

                    # Pauses if more than 5 products are processed, awaiting user confirmation.
                    if total_processed > 5:
                        update_session_status(
                            session_id,
                            "awaiting_confirmation",
                            [(url, cat["name"]) for url in cat_urls],
                            "awaiting_confirmation",
                        )
                        log_message(
                            session_id,
                            f"Found {total_processed} products, awaiting confirmation",
                            level="warning",
                        )
                        result["products_processed"] = total_processed
                        result["message"] = (
                            f"⚠️ Paused for confirmation: {total_processed} products processed"
                        )
                        return result

            result["success"] = True
            result["products_processed"] = total_processed
            result["message"] = (
                f"✅ Successfully parsed {total_processed} products across all categories"
            )

        # If parsing was successful, updates the session status to 'completed' and logs a final success message.
        if result["success"]:
            update_session_status(session_id, "completed", progress="done")
            log_message(
                session_id,
                f"✅ Parsing completed successfully: {result['products_processed']} products processed",
                level="info",
            )
        return result

    except RequestException as e:
        log_message(session_id, f"Network error during parsing: {e}", level="error")
        result["message"] = f"Network error: {e}"
    except SQLiteError as e:
        log_message(session_id, f"Database error during parsing: {e}", level="error")
        result["message"] = f"Database error: {e}"
    except Exception as e:
        log_message(
            session_id,
            f"Unexpected error during parsing: {e}\n{traceback.format_exc()}",
            level="error",
        )
        update_session_status(session_id, "error")
        cleanup_incomplete(session_id)
        result["message"] = f"Unexpected error: {e}"
    return result


def parse_product_urls(
    product_urls: list[str | tuple],
    category: Optional[str],
    session_id: Optional[str],
    cancel_flags: Optional[dict[str, bool]],
    static_folder: Optional[str],
) -> Dict[str, Union[bool, int, str]]:
    """Process a list of product URLs and save parsed data to the database.

    This function iterates through a list of product URLs, fetches and extracts data
    for each product, and saves the results to the database. It supports cancellation
    via the cancel_flags dictionary.

    Args:
        product_urls: List of product URLs or tuples (URL, category).
        category: Default category to assign if not provided in product_urls.
        session_id: Unique identifier for the parsing session.
        cancel_flags: Dictionary tracking cancellation status for sessions.
        static_folder: Path to the static folder for saving images.

    Returns:
        Dict[str, Union[bool, int, str]]: A dictionary containing:
            - success (bool): Whether all products were processed successfully.
            - products_processed (int): Number of products successfully parsed.
            - message (str): Summary message for the processing outcome.

    Raises:
        ValueError: If required inputs are invalid.
    """
    # Input validation
    if not session_id or not isinstance(session_id, str):
        raise ValueError("session_id must be a non-empty string")
    if not product_urls or not isinstance(product_urls, list):
        raise ValueError("product_urls must be a non-empty list")
    if cancel_flags is None:
        raise ValueError("cancel_flags dictionary is required")
    if static_folder is not None and not isinstance(static_folder, str):
        raise ValueError("static_folder must be a string")

    log_message(
        session_id,
        f"Processing {len(product_urls)} product URLs, static_folder={static_folder}",
        level="debug",
    )
    result = {"success": True, "products_processed": 0, "message": ""}
    for item_url in product_urls:
        with cancel_lock:
            if cancel_flags.get(session_id, False):
                log_message(
                    session_id,
                    "Parsing canceled, stopping product processing",
                    level="warning",
                )
                result["message"] = "Parsing canceled"
                return result

        url = item_url[0] if isinstance(item_url, tuple) else item_url
        cat = item_url[1] if isinstance(item_url, tuple) else category
        log_message(
            session_id,
            f"Processing product URL: {url} (category: {cat})",
            level="debug",
        )

        try:
            time.sleep(1)  # Rate limiting
            log_message(session_id, f"Fetching product: {url}", level="debug")
            product = fetch_product_page(
                url, cat, session_id, cancel_flags, static_folder
            )
            if product is None:
                log_message(
                    session_id,
                    f"Failed to fetch or parse product {url}: returned None (check selectors in data_fetcher.py)",
                    level="error",
                )
                result["success"] = False
                continue
            log_message(
                session_id, f"Product fetched: {product.to_dict()}", level="debug"
            )
            if save_to_db(product, product.variants, session_id, cancel_flags):
                log_message(
                    session_id,
                    f"Successfully saved: {product.to_dict()}",
                    level="info",
                )
                result["products_processed"] += 1
            else:
                log_message(
                    session_id,
                    f"Error saving product {url}: check database logs in save_to_db",
                    level="error",
                )
                result["success"] = False
        except RequestException as e:
            log_message(
                session_id,
                f"Network error processing product {url}: {e} (check URL or connectivity)",
                level="error",
            )
            result["success"] = False
        except SQLiteError as e:
            log_message(
                session_id,
                f"Database error processing product {url}: {e} (check schema or locks)",
                level="error",
            )
            result["success"] = False
        except Exception as e:
            log_message(
                session_id,
                f"Unexpected error processing product {url}: {e}\n{traceback.format_exc()}",
                level="error",
            )
            result["success"] = False

    if result["products_processed"] == len(product_urls) and result["success"]:
        result["message"] = (
            f"Successfully processed {result['products_processed']} products"
        )
    else:
        result["message"] = (
            f"Processed {result['products_processed']} of {len(product_urls)} products with errors"
        )
    log_message(
        session_id,
        result["message"],
        level="info" if result["success"] else "warning",
    )
    return result
