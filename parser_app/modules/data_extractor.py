from datetime import datetime

# Import modules
from .classes import Variant
from .logger import log_message
from .data_image_handler import download_image


def extract_flexible_field(label_text, soup):
    fields = soup.find_all("div", class_="field")
    for field in fields:
        label_div = field.find("div", class_="field-label")
        inline_label_div = field.find("div", class_="field-label-inline-first")

        if label_div and label_text in label_div.text:
            value = field.find("div", class_="field-item")
            if value:
                return value.get_text(strip=True)

        elif inline_label_div and label_text in inline_label_div.text:
            value_parent = inline_label_div.parent
            if value_parent:
                full_text = value_parent.get_text(strip=True)
                label_text_clean = inline_label_div.get_text(strip=True)
                return full_text.replace(label_text_clean, "").strip()
    return "Не найдено"


def extract_main_image(soup):
    image_container = soup.find(
        "div", class_="field field-type-filefield field-field-yarn-foto"
    )
    if image_container:
        link = image_container.find("a", href=True)
        if link and link["href"]:
            image_url = (
                link["href"]
                if link["href"].startswith("http")
                else "https://nsk-mahaon.ru" + link["href"]
            )
            return image_url
    return None


def extract_variants(
    soup,
    product_id,
    image_folder,
    existing_variant_paths,
    session_id,
    cancel_flags,
    static_folder,
):
    variants = []
    samples_container = soup.find("div", id="samples")
    if samples_container:
        samples = samples_container.find_all("div", class_="sample")
        for sample in samples:
            if cancel_flags.get(session_id, False):
                log_message(
                    session_id,
                    "⚠️ Парсинг отменен, прекращение извлечения вариантов | extract_variants(...)",
                    level="warning",
                )
                break
            article_number = sample.find("span", class_="sample-number")
            article_number = (
                article_number.get_text(strip=True) if article_number else "Не найдено"
            )

            variant_name = sample.find("span", class_="sample-name")
            variant_name = (
                variant_name.get_text(strip=True) if variant_name else "Не найдено"
            )

            add_cart_link = sample.find("div", class_="add-cart-link")
            no_exist_div = sample.find("div", class_="no-exist")
            is_available = bool(add_cart_link) and (
                not no_exist_div or no_exist_div.get_text(strip=True) != "(нет)"
            )

            sample_img = sample.find("div", class_="sample-img")
            image_url = None
            if sample_img:
                link = sample_img.find("a", href=True)
                if link and link["href"]:
                    image_url = (
                        link["href"]
                        if link["href"].startswith("http")
                        else "https://nsk-mahaon.ru" + link["href"]
                    )

            variant_key = f"{article_number}_{variant_name}"
            existing_path = existing_variant_paths.get(variant_key)

            image_path = (
                download_image(
                    image_url,
                    f"variant_{article_number}_{variant_name}",
                    image_folder,
                    static_folder,
                    existing_path,
                    session_id,
                )
                if image_url
                else None
            )

            variant = Variant(
                product_id=product_id,
                article_number=article_number,
                variant_name=variant_name,
                is_available=is_available,
                image_url=image_url,
                image_path=image_path,
            )
            variant.last_updated = datetime.now().isoformat(" ", "minutes")
            variants.append(variant)
            log_message(
                session_id,
                f"Извлечен вариант: {variant_name} (Артикул: {article_number}) | extract_variants(...)",
                level="info",
            )
    return variants
