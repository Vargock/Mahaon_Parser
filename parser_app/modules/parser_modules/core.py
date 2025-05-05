# Import modules
from ..logger import log_message
from ..db_write import update_session_status, save_to_db, cleanup_incomplete
from .scraper import scrape_categories, scrape_catalog_page, scrape_product_page


def parse_catalog(
    catalog_url=None,
    category=None,
    max_pages=None,
    max_products=None,
    session_id=None,
    url=None,
    cancel_flags=None,
    static_folder=None,
):
    log_message(
        session_id,
        f"Начало парсинга: URL={url}, Категория={category}, Каталог={catalog_url}",
        level="debug",
    )
    update_session_status(session_id, "in_progress", progress="collecting_urls")

    try:
        if url and "/products/" in url:
            # Parse single product
            product = scrape_product_page(
                url, category or "Unknown", session_id, cancel_flags, static_folder
            )
            if product and save_to_db(
                product, product.variants, session_id, cancel_flags
            ):
                log_message(
                    session_id,
                    f"✅ Успешно сохранен продукт: {product.title}",
                    level="info",
                )
            else:
                log_message(
                    session_id,
                    f"❌ Ошибка при обработке продукта: {url}",
                    level="error",
                )
        elif url and "/collection/" in url:
            # Parse specific category via URL
            product_urls = scrape_catalog_page(
                url,
                category or "Unknown",
                max_pages,
                max_products,
                session_id,
                cancel_flags,
            )
            log_message(
                session_id,
                f"Found {len(product_urls)} product URLs in category",
                level="debug",
            )
            if len(product_urls) > 5:
                update_session_status(
                    session_id,
                    "awaiting_confirmation",
                    product_urls,
                    "awaiting_confirmation",
                )
                log_message(
                    session_id,
                    f"🛑 Найдено {len(product_urls)} продуктов, требуется подтверждение",
                    level="warning",
                )
                return
            parse_product_urls(
                product_urls, category or "Unknown", session_id, cancel_flags
            )
        elif catalog_url:
            # Parse selected category
            product_urls = scrape_catalog_page(
                catalog_url, category, max_pages, max_products, session_id, cancel_flags
            )
            log_message(
                session_id,
                f"Found {len(product_urls, level="debug")} product URLs in catalog",
                level="info",
            )
            if len(product_urls) > 5:
                update_session_status(
                    session_id,
                    "awaiting_confirmation",
                    product_urls,
                    "awaiting_confirmation",
                )
                log_message(
                    session_id,
                    f"🛑 Найдено {len(product_urls)} продуктов, требуется подтверждение",
                    level="warning",
                )
                return
            parse_product_urls(product_urls, category, session_id, cancel_flags)
        else:
            # Parse all categories
            categories = scrape_categories()
            log_message(
                session_id,
                f"Found {len(categories, level="debug")} categories to parse",
                level="info",
            )
            total_products = 0
            product_urls = []
            for cat in categories:
                if max_products and total_products >= max_products:
                    log_message(
                        session_id,
                        f"Достигнут лимит продуктов ({max_products})",
                        level="debug",
                    )
                    break
                if cancel_flags.get(session_id, False):
                    log_message(
                        session_id,
                        "⚠️ Парсинг отменен, прекращение парсинга категорий",
                        level="warning",
                    )
                    break
                cat_urls = scrape_catalog_page(
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
                update_session_status(
                    session_id,
                    "awaiting_confirmation",
                    product_urls,
                    "awaiting_confirmation",
                )
                log_message(
                    session_id,
                    f"🛑 Найдено {total_products} продуктов, требуется подтверждение",
                    level="warning",
                )
                return
            parse_product_urls(product_urls, None, session_id, cancel_flags)
    except Exception as e:
        log_message(session_id, f"❌ Ошибка во время парсинга: {e}", level="error")
        update_session_status(session_id, "error")
        cleanup_incomplete(session_id)


def parse_product_urls(product_urls, category, session_id, cancel_flags, static_folder):
    log_message(
        session_id, f"Processing {len(product_urls)} product URLs", level="debug"
    )
    for item in product_urls:
        if cancel_flags.get(session_id, False):
            log_message(
                session_id,
                "⚠️ Парсинг отменен, прекращение обработки продуктов",
                level="warning",
            )
            break
        url = item[0] if isinstance(item, tuple) else item
        cat = item[1] if isinstance(item, tuple) else category
        try:
            product = scrape_product_page(
                url, cat, session_id, cancel_flags, static_folder
            )
            if product and save_to_db(
                product, product.variants, session_id, cancel_flags
            ):
                log_message(
                    session_id,
                    f"✅ Успешно сохранено: {product.to_dict()}",
                    level="info",
                )
            else:
                log_message(
                    session_id,
                    f"❌ Ошибка при обработке продукта: {url}",
                    level="error",
                )
        except Exception as e:
            log_message(
                session_id,
                f"❌ Ошибка при обработке продукта {url}: {e}",
                level="error",
            )
