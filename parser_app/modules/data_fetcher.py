import requests
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from .classes import Product
from .logger import log_message
from .utilities import get_image_folder
from .db_read import get_existing_image_paths
from .data_image_handler import download_image
from .data_extractor import extract_flexible_field, extract_main_image, extract_variants


def fetch_product_page(url, category, session_id, cancel_flags, static_folder):
    if cancel_flags.get(session_id, False):
        log_message(session_id, "⚠️ Парсинг отменен, пропуск продукта", level="warning")
        return None

    log_message(session_id, f"Начало парсинга продукта: {url}", level="info")

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except Exception as e:
        log_message(
            session_id,
            f"❌ Ошибка при запросе страницы продукта {url}: {e}",
            level="error",
        )
        log_message()
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    product = Product(url)

    product.title = (
        soup.find("h1", class_="page-title").get_text(strip=True)
        if soup.find("h1", class_="page-title")
        else "Не найдено"
    )
    product.price = (
        soup.find("span", class_="price").get_text(strip=True)
        if soup.find("span", class_="price")
        else "Не найдено"
    )

    product.sostav = extract_flexible_field("Состав", soup)
    product.ves_motka = extract_flexible_field("Вес мотка", soup)
    product.dlina_motka = extract_flexible_field("Длина мотка", soup)
    product.ves_upakovki = extract_flexible_field("Вес упаковки", soup)
    product.category = category
    product.last_updated = datetime.now().isoformat(" ", "minutes")

    image_folder, product_name = get_image_folder(url)
    existing_main_path, existing_variant_paths = get_existing_image_paths(url)

    product.image_url = extract_main_image(soup)
    product.image_path = (
        download_image(
            product.image_url,
            f"main_{product_name}",
            image_folder,
            static_folder,
            existing_main_path,
            session_id,
        )
        if product.image_url
        else None
    )

    product.variants = extract_variants(
        soup,
        product_id=0,
        image_folder=image_folder,
        existing_variant_paths=existing_variant_paths,
        session_id=session_id,
        cancel_flags=cancel_flags,
        static_folder=static_folder,
    )

    log_message(
        session_id, f"Completed parsing product: {product.title}", level="debug"
    )
    return product


def fetch_catalog_page(
    catalog_url,
    category,
    max_pages=None,
    max_products=None,
    session_id=None,
    cancel_flags=None,
):
    if cancel_flags.get(session_id, False):
        log_message(session_id, "⚠️ Парсинг отменен, пропуск каталога", level="warning")
        return []

    product_urls = []
    base_url = "https://nsk-mahaon.ru"
    page_count = 0

    while catalog_url:
        if max_pages is not None and page_count >= max_pages:
            log_message(
                session_id,
                f"Достигнут лимит страниц ({max_pages}). Прекращение парсинга.",
                level="info",
            )
            break
        if cancel_flags.get(session_id, False):
            log_message(
                session_id,
                "⚠️ Парсинг отменен, прекращение парсинга каталога",
                level="warning",
            )
            break

        log_message(
            session_id, f"Парсинг страницы каталога: {catalog_url}", level="debug"
        )
        try:
            response = requests.get(catalog_url, timeout=10)
            response.raise_for_status()
        except Exception as e:
            log_message(
                session_id,
                f"❌ Ошибка при запросе каталога {catalog_url}: {e}",
                level="error",
            )
            break

        soup = BeautifulSoup(response.text, "html.parser")

        table = soup.find("table", class_="views-table cols-7")
        if not table:
            log_message(
                session_id,
                "❌ Ошибка: Таблица 'views-table cols-7' не найдена на странице.",
                level="error",
            )
            table = soup.find("table")
            if not table:
                log_message(
                    session_id,
                    "❌ Ошибка: Никакая таблица не найдена на странице.",
                    level="error",
                )
                break
            else:
                log_message(
                    session_id, "Найдена альтернативная таблица.", level="error"
                )

        tbody = table.find("tbody")
        if not tbody:
            log_message(
                session_id,
                "❌ Ошибка: Элемент <tbody> не найден в таблице.",
                level="error",
            )
            break

        rows = tbody.find_all("tr")
        if not rows:
            log_message(
                session_id,
                "❌ Ошибка: Строки <tr> не найдены в <tbody>.",
                level="error",
            )
            break

        log_message(session_id, f"Найдено {len(rows)} строк в таблице.", level="info")
        for row in rows:
            title_cell = row.find("td", class_="views-field views-field-title active")
            if title_cell:
                link = title_cell.find("a", href=True)
                if link and link["href"]:
                    product_url = urljoin(base_url, link["href"])
                    log_message(
                        session_id, f"Найден продукт: {product_url}", level="info"
                    )
                    if product_url not in product_urls:
                        product_urls.append(product_url)
                        log_message(
                            session_id,
                            f"Проверка длины {len(product_urls)}",
                            level="debug",
                        )
                        if (
                            max_products is not None
                            and len(product_urls) >= max_products
                        ):
                            log_message(
                                session_id,
                                f"Длина составляет {len(product_urls)}",
                                level="debug",
                            )
                            log_message(
                                session_id,
                                f"Достигнут лимит продуктов ({max_products}). Прекращение парсинга.",
                                level="info",
                            )
                            return product_urls

                else:
                    log_message(
                        session_id,
                        "⚠️ Предупреждение: Ссылка не найдена в ячейке заголовка.",
                        level="warning",
                    )
            else:
                log_message(
                    session_id,
                    "⚠️ Предупреждение: Ячейка заголовка не найдена в строке.",
                    level="warning",
                )

        page_count += 1

        next_page = soup.find("li", class_="pager-next")
        if next_page:
            link = next_page.find("a", href=True)
            if link and link["href"]:
                catalog_url = urljoin(base_url, link["href"])
                log_message(
                    session_id,
                    f"Найдена следующая страница: {catalog_url}",
                    level="info",
                )
            else:
                log_message(
                    session_id,
                    "Следующая страница не найдена (нет ссылки в pager-next). Завершение пагинации.",
                    level="info",
                )
                catalog_url = None
        else:
            log_message(
                session_id,
                "Следующая страница не найдена (нет pager-next). Завершение пагинации.",
                level="info",
            )
            catalog_url = None

    log_message(
        session_id,
        f"Завершена fetch_catalog_page(), возвращает product_urls, длинной {len(product_urls)}",
        level="debug",
    )
    return product_urls


def fetch_categories():
    url = "https://nsk-mahaon.ru/"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        categories = []
        catalog_block = soup.find("div", id="block-block-4")
        if catalog_block:
            menu = catalog_block.find("ul", class_="menu catalog-menu level-0")
            if menu:
                for li in menu.find_all("li", recursive=False):
                    if "hide" not in li.get("class", []):
                        link = li.find("a", href=True)
                        if link and link["href"]:
                            category_name = link.get_text(strip=True)
                            category_url = urljoin(
                                "https://nsk-mahaon.ru", link["href"]
                            )
                            categories.append(
                                {"name": category_name, "url": category_url}
                            )
        if not categories:
            log_message("Категории не найдены в блоке #block-block-4", level="warning")
        return categories
    except Exception as e:
        log_message(f"Ошибка при получении категорий: {e}", level="error")
        return []
