class Product:
    def __init__(self, url):
        self.url = url
        self.title = None
        self.price = None
        self.sostav = None
        self.ves_motka = None
        self.dlina_motka = None
        self.ves_upakovki = None
        self.image_url = None
        self.image_path = None
        self.category = None
        self.last_updated = None
        self.variants = []

    def to_dict(self):
        return {
            "url": self.url,
            "title": self.title,
            "price": self.price,
            "sostav": self.sostav,
            "ves_motka": self.ves_motka,
            "dlina_motka": self.dlina_motka,
            "ves_upakovki": self.ves_upakovki,
            "image_path": self.image_path,
            "category": self.category,
            "last_updated": self.last_updated,
        }


class Variant:
    def __init__(
        self,
        product_id,
        article_number,
        variant_name,
        is_available,
        image_url,
        image_path,
    ):
        self.product_id = product_id
        self.article_number = article_number
        self.variant_name = variant_name
        self.is_available = is_available
        self.image_url = image_url
        self.image_path = image_path
        self.last_updated = None

    def to_dict(self):
        return {
            "product_id": self.product_id,
            "article_number": self.article_number,
            "variant_name": self.variant_name,
            "is_available": self.is_available,
            "image_path": self.image_path,
            "image_url": self.image_url,
            "last_updated": self.last_updated,
        }
