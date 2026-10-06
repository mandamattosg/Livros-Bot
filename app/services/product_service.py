from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.amazon.client import AmazonClient
from app.config import settings
from app.models.product import Product
from app.models.user import User
from app.models.user_product import UserProduct
from app.services.price_service import PriceService
from app.utils.parse_link import extract_asin

ALREADY_MONITORED_MESSAGE = "Você já está monitorando este livro."



class ProductService:
    """Serviço responsável pelo cadastro e associação de produtos a usuários."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.amazon_client = AmazonClient()
        self.price_service = PriceService(db)

    def get_or_create_user(self, telegram_id: str, username: str | None = None, first_name: str | None = None) -> User:
        user = self.db.query(User).filter(User.telegram_id == telegram_id).first()
        if user is None:
            user = User(telegram_id=telegram_id, username=username, first_name=first_name)
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
        return user

    def register_product(self, user_id: str, link: str) -> tuple[Product | None, str]:
        """Registra um produto a partir de um link da Amazon e associa ao usuário."""

        asin = extract_asin(link)
        if not asin:
            return None, "Link inválido da Amazon."

        existing_product = self.db.query(Product).filter(Product.asin == asin).first()
        if existing_product is None:
            try:
                data = self.amazon_client.get_items([asin])
            except Exception as exc:
                return None, f"Não foi possível consultar a Amazon no momento: {exc}"

            items = data.get("itemsResult", {}).get("items", [])
            if not items:
                return None, "Não foi possível encontrar o produto na Amazon."

            item = items[0]
            # Temporariamente desativado: a regra de identificação de livros ainda não está confiável.
            # if not self._is_book_item(item):
            #     return None, "Este bot só monitora livros. Envie um link de livro da Amazon."

            title = self.amazon_client.extract_title(item)
            image_url = self.amazon_client.extract_image(item)
            affiliate_link = item.get("detailPageURL")

            product = Product(
                asin=asin,
                title=title,
                image_url=image_url,
                affiliate_link=affiliate_link,
            )
            self.db.add(product)
            self.db.commit()
            self.db.refresh(product)

            price = self.amazon_client.extract_price(item)
            if price is not None:
                self.price_service.record_price(product, price)
        else:
            product = existing_product

        user = self.get_or_create_user(telegram_id=user_id)
        existing_relation = self.db.query(UserProduct).filter(
            UserProduct.user_id == user.id,
            UserProduct.product_id == product.id,
        ).first()
        current_count = (
            self.db.query(UserProduct)
            .filter(UserProduct.user_id == user.id)
            .count()
        )
        monitor_limit = max(int(settings.USER_PRODUCT_MONITOR_LIMIT), 1)
        if current_count >= monitor_limit and existing_relation is None:
            return None, (
                f"Você já atingiu o limite de {monitor_limit} produtos monitorados. "
                "Remova um produto para cadastrar outro. Use o comando /remover"
            )
        if existing_relation is not None:
            return product, ALREADY_MONITORED_MESSAGE
        relation = UserProduct(user_id=user.id, product_id=product.id)
        self.db.add(relation)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            return product, ALREADY_MONITORED_MESSAGE

        return product, "Produto cadastrado com sucesso."

    def _is_book_item(self, item: dict) -> bool:
        """Tenta identificar se o item retornado pela Amazon é um livro usando BrowseNodes e ISBN."""

        detail_page_url = item.get("detailPageURL") or ""
        url_lower = detail_page_url.lower()

        if "/books/" in url_lower or "/kindle-store/" in url_lower or "/audible/" in url_lower:
            return True

        browse_nodes = self.amazon_client.extract_browse_nodes(item)
        browse_nodes_lower = [node.lower() for node in browse_nodes]
        if any(keyword in browse_nodes_lower for keyword in ["books", "kindle store", "ebooks kindle", "livros", "kindle"]):
            return True

        external_ids = self.amazon_client.extract_external_ids(item)
        if external_ids:
            return True

        item_info = item.get("itemInfo", {})
        title = item_info.get("title", {}).get("displayValue") or item_info.get("title", {}).get("value") or ""
        title_lower = title.lower()

        non_book_keywords = (
            "iphone",
            "smartphone",
            "celular",
            "phone",
            "tablet",
            "notebook",
            "laptop",
            "tv",
            "monitor",
            "console",
            "headphone",
            "earbuds",
            "airpods",
            "câmera",
            "camera",
            "fone",
            "mouse",
            "teclado",
            "keyboard",
            "impressora",
            "printer",
            "refrigerador",
            "geladeira",
            "smartwatch",
            "relógio",
            "speaker",
            "caixa de som",
            "carregador",
            "powerbank",
            "aspirador",
            "vacuum",
            "ração",
            "racao",
            "ração úmida",
            "pet",
            "cachorro",
            "cães",
            "caes",
            "gato",
            "ração para",
            "sachê",
            "sache",
            "alimento",
            "comida",
            "shampoo",
            "perfume",
            "escova",
            "escova de cabelo",
            "caneca",
            "mug",
            "camiseta",
            "bone",
            "sapato",
        )
        if any(keyword in title_lower for keyword in non_book_keywords):
            return False

        book_keywords = ("livro", "ebook", "kindle", "audiobook", "novela", "romance", "conto", "biografia", "poesia", "manual", "guia")
        if any(keyword in title_lower for keyword in book_keywords):
            return True

        if title_lower and len(title_lower.split()) <= 6:
            return True

        return False

    def list_products(self, user_id: str) -> list[Product]:
        """Retorna todos os produtos associados a um usuário."""

        user = self.get_or_create_user(telegram_id=user_id)
        return (
            self.db.query(Product)
            .join(UserProduct, UserProduct.product_id == Product.id)
            .filter(UserProduct.user_id == user.id)
            .order_by(UserProduct.created_at.asc())
            .all()
        )

    def remove_product(self, user_id: str, selection: str) -> tuple[bool, str]:
        """Remove um produto da lista do usuário com base em um índice ou no ID do produto."""

        try:
            selection_id = int(selection)
        except ValueError:
            return False, "Informe o número do produto que deseja remover."

        user = self.get_or_create_user(telegram_id=user_id)
        relations = (
            self.db.query(UserProduct)
            .filter(UserProduct.user_id == user.id)
            .order_by(UserProduct.created_at.asc())
            .all()
        )

        for relation in relations:
            if relation.product_id == selection_id:
                self.db.delete(relation)
                self.db.commit()
                return True, "Livro removido da sua lista."

        index = selection_id - 1
        if not 0 <= index < len(relations):
            return False, "Índice inválido. Use um número da lista exibida."

        relation = relations[index]
        self.db.delete(relation)
        self.db.commit()
        return True, "Livro removido da sua lista."
