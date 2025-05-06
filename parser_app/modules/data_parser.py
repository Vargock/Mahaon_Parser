# data_parser.py
"""Module for orchestrating the parsing of web data in the Parser app.

This module coordinates the high-level parsing process, integrating data fetching,
extraction, and storage. It handles parsing of single products, specific categories,
or all categories, ensuring data is structured and saved to the database.
"""

# Standard library imports
from typing import Optional

# Local imports
from .logger import log_message
from .db_write import update_session_status, save_to_db, cleanup_incomplete
from .data_fetcher import fetch_categories, fetch_catalog_page, fetch_product_page


def parse_catalog(
    catalog_url: Optional[str] = None,
    category: Optional[str] = None,
    max_pages: Optional[int] = None,
    max_products: Optional[int] = None,
    session_id: Optional[str] = None,
    url: Optional[str] = None,
    cancel_flags: Optional[dict[str, bool]] = None,
    static_folder: Optional[str] = None,
) -> None:
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

    Raises:
        Exception: If an error occurs during parsing, it is logged and the session
            status is updated to 'error'.
    """
    log_message(
        session_id,
        f"parse_catalog() | Starting parsing: "
        f"{'URL: ' + url if url else ''} "
        f"{'Category: ' + category if category else ''}, "
        f"Catalog = {catalog_url}, "
        f"{'Max Pages: ' + str(max_pages) if max_pages else ''}, "
        f"{'Max Products: ' + str(max_products) if max_products else ''}",
        level="debug",
    )
    update_session_status(session_id, "in_progress", progress="collecting_urls")

    try:
        if url and "/products/" in url:
            # Handle single product parsing
            product = fetch_product_page(
                url, category or "Unknown", session_id, cancel_flags, static_folder
            )
            if product and save_to_db(
                product, product.variants, session_id, cancel_flags
            ):
                log_message(
                    session_id,
                    f"parse_catalog() | Successfully saved product: {product.title}",
                    level="info",
                )
            else:
                log_message(
                    session_id,
                    f"parse_catalog() | Error processing product: {url}",
                    level="error",
                )
        elif url and "/collection/" in url:
            # Parse a specific category via collection URL
            product_urls = fetch_catalog_page(
                url,
                category or "Unknown",
                max_pages,
                max_products,
                session_id,
                cancel_flags,
            )
            log_message(
                session_id,
                f"parse_catalog() | Found {len(product_urls)} product URLs in category",
                level="debug",
            )
            if len(product_urls) > 5:
                # Pause for confirmation if too many products are found
                update_session_status(
                    session_id,
                    "awaiting_confirmation",
                    product_urls,
                    "awaiting_confirmation",
                )
                log_message(
                    session_id,
                    f"parse_catalog() | Found {len(product_urls)} products, awaiting confirmation",
                    level="warning",
                )
                return
            parse_product_urls(
                product_urls,
                category or "Unknown",
                session_id,
                cancel_flags,
                static_folder,
            )
        elif catalog_url:
            # Parse a selected category
            product_urls = fetch_catalog_page(
                catalog_url, category, max_pages, max_products, session_id, cancel_flags
            )
            log_message(
                session_id,
                f"parse_catalog() | Found {len(product_urls)} product URLs in catalog",
                level="info",
            )
            if len(product_urls) > 5:
                # Pause for confirmation if too many products are found
                update_session_status(
                    session_id,
                    "awaiting_confirmation",
                    product_urls,
                    "awaiting_confirmation",
                )
                log_message(
                    session_id,
                    f"parse_catalog() | Found {len(product_urls)} products, awaiting confirmation",
                    level="warning",
                )
                return
            parse_product_urls(
                product_urls, category, session_id, cancel_flags, static_folder
            )
        else:
            # Parse all categories
            categories = fetch_categories()
            log_message(
                session_id,
                f"parse_catalog() | Found {len(categories)} categories to parse",
                level="info",
            )
            total_products = 0
            product_urls = []
            for cat in categories:
                if max_products and total_products >= max_products:
                    log_message(
                        session_id,
                        f"parse_catalog() | Reached product limit ({max_products})",
                        level="debug",
                    )
                    break
                if cancel_flags.get(session_id, False):
                    log_message(
                        session_id,
                        "parse_catalog() | Parsing canceled, stopping category parsing",
                        level="warning",
                    )
                    break
                cat_urls = fetch_catalog_page(
                    cat["url"],
                    cat["name"],
                    max_pages,
                    max_products - total_products,
                    session_id,
                    cancel_flags,
                )
                product_urls.extend([(url, cat["name"]) for url in cat_urls])
                total_products += len(cat_urls)
            if total_products > 5:
                # Pause for confirmation if too many products are found
                update_session_status(
                    session_id,
                    "awaiting_confirmation",
                    product_urls,
                    "awaiting_confirmation",
                )
                log_message(
                    session_id,
                    f"parse_catalog() | Found {total_products} products, awaiting confirmation",
                    level="warning",
                )
                return
            parse_product_urls(
                product_urls, None, session_id, cancel_flags, static_folder
            )
    except Exception as e:
        log_message(
            session_id,
            f"parse_catalog() | Error during parsing: {e}",
            level="error",
        )
        update_session_status(session_id, "error")
        cleanup_incomplete(session_id)


def parse_product_urls(
    product_urls: list[str | tuple],
    category: Optional[str],
    session_id: Optional[str],
    cancel_flags: Optional[dict[str, bool]],
    static_folder: Optional[str],
) -> None:
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

    Raises:
        Exception: If an error occurs during processing, it is logged and the loop
            continues with the next URL.
    """
    log_message(
        session_id,
        f"parse_product_urls() | Processing {len(product_urls)} product URLs",
        level="debug",
    )
    for item_url in product_urls:
        if cancel_flags.get(session_id, False):
            log_message(
                session_id,
                "parse_product_urls() | Parsing canceled, stopping product processing",
                level="warning",
            )
            break

        # Extract URL and category from item_url (tuple or string)
        url = item_url[0] if isinstance(item_url, tuple) else item_url
        cat = item_url[1] if isinstance(item_url, tuple) else category

        try:
            product = fetch_product_page(
                url, cat, session_id, cancel_flags, static_folder
            )
            if product and save_to_db(
                product, product.variants, session_id, cancel_flags
            ):
                log_message(
                    session_id,
                    f"parse_product_urls() | Successfully saved: {product.to_dict()}",
                    level="info",
                )
            else:
                log_message(
                    session_id,
                    f"parse_product_urls() | Error processing product: {url}",
                    level="error",
                )
        except Exception as e:
            log_message(
                session_id,
                f"parse_product_urls() | Error processing product {url}: {e}",
                level="error",
            )
