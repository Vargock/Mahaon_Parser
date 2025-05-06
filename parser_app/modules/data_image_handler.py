import os
import requests

# Import modules
from .logger import log_message
from .utilities import normalize_image_path, sanitize_filename


def download_image(
    image_url,
    filename_prefix,
    folder,
    static_folder,
    existing_path=None,
    session_id=None,
):
    existing_path = normalize_image_path(existing_path)
    if existing_path and os.path.exists(os.path.join(static_folder, existing_path)):
        log_message(
            session_id,
            f"Изображение уже существует: {existing_path} | download_image()",
            level="debug",
        )
        return existing_path

    relative_path = os.path.join(
        folder, f"{sanitize_filename(filename_prefix)}.jpg"
    ).replace(os.sep, "/")
    filepath = os.path.join(static_folder, relative_path)

    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    if not os.path.exists(filepath):
        try:
            response = requests.get(image_url, timeout=10)
            response.raise_for_status()
            with open(filepath, "wb") as f:
                f.write(response.content)
            log_message(
                session_id, f"Изображение загружено: {relative_path}", level="debug"
            )
            return os.path.join("static", relative_path).replace(os.sep, "/")
        except Exception as e:
            log_message(
                session_id,
                f"❌ Ошибка загрузки изображения {image_url}: {e} | download_image()",
                level="error",
            )
    else:
        log_message(
            session_id,
            f"Изображение уже существует: {relative_path} | download_image()",
            level="debug",
        )
        return os.path.join("static", relative_path).replace(os.sep, "/")
    return None
