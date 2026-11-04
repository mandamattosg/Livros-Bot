import unittest
from unittest.mock import patch

from app.config import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.product import Product
from app.models.user import User
from app.models.user_product import UserProduct
from app.services.product_service import ProductService


class ProductServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
        self.session = self.Session()
        self.service = ProductService(self.session)

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(self.engine)

    def test_register_product_creates_user_and_relation(self) -> None:
        mocked_items = {
            "itemsResult": {
                "items": [
                    {
                        "detailPageURL": "https://example.com",
                        "itemInfo": {"title": {"displayValue": "Livro Teste"}},
                        "images": {"primary": {"large": {"url": "https://img.test"}}},
                        "offersV2": {
                            "listings": [
                                {"price": {"money": {"amount": 39.9, "currency": "BRL"}}}
                            ]
                        },
                    }
                ]
            }
        }
        with patch.object(self.service.amazon_client, "get_items", return_value=mocked_items):
            product, message = self.service.register_product("123", "https://www.amazon.com.br/dp/6528101965")

        self.assertEqual(message, "Produto cadastrado com sucesso.")
        self.assertIsNotNone(product)
        self.assertEqual(product.asin, "6528101965")
        self.assertEqual(self.session.query(User).count(), 1)
        self.assertEqual(self.session.query(Product).count(), 1)
        self.assertEqual(self.session.query(UserProduct).count(), 1)
        self.assertEqual(self.session.query(Product).first().id, product.id)
        self.assertEqual(self.session.query(Product).first().asin, "6528101965")

    def test_register_product_accepts_non_book_items_temporarily(self) -> None:
        mocked_items = {
            "itemsResult": {
                "items": [
                    {
                        "detailPageURL": "https://www.amazon.com.br/dp/B09XQZQK7Q",
                        "itemInfo": {"title": {"displayValue": "iPhone 15 Pro Max"}},
                        "images": {"primary": {"large": {"url": "https://img.test"}}},
                        "offersV2": {"listings": [{"price": {"money": {"amount": 9999, "currency": "BRL"}}}]},
                    }
                ]
            }
        }
        with patch.object(self.service.amazon_client, "get_items", return_value=mocked_items):
            product, message = self.service.register_product("123", "https://www.amazon.com.br/dp/B09XQZQK7Q")

        self.assertIsNotNone(product)
        self.assertEqual(message, "Produto cadastrado com sucesso.")

    def test_register_product_accepts_pet_food_items_temporarily(self) -> None:
        mocked_items = {
            "itemsResult": {
                "items": [
                    {
                        "detailPageURL": "https://www.amazon.com.br/dp/B0ADBXXM01",
                        "itemInfo": {"title": {"displayValue": "Pack Ração Úmida Pedigree Sachê Carne/Frango/Cordeiro para Cães Adultos de Raças Pequenas - Leve 24 Pague 18"}},
                        "images": {"primary": {"large": {"url": "https://img.test"}}},
                        "offersV2": {"listings": [{"price": {"money": {"amount": 49.9, "currency": "BRL"}}}]},
                    }
                ]
            }
        }
        with patch.object(self.service.amazon_client, "get_items", return_value=mocked_items):
            product, message = self.service.register_product("123", "https://www.amazon.com.br/dp/B0ADBXXM01")

        self.assertIsNotNone(product)
        self.assertEqual(message, "Produto cadastrado com sucesso.")

    def test_register_product_rejects_when_user_reaches_limit(self) -> None:
        for index in range(10):
            mocked_items = {
                "itemsResult": {
                    "items": [
                        {
                            "detailPageURL": f"https://www.amazon.com.br/dp/652810196{index}",
                            "itemInfo": {"title": {"displayValue": f"Livro {index}"}},
                            "images": {"primary": {"large": {"url": "https://img.test"}}},
                            "offersV2": {"listings": [{"price": {"money": {"amount": 39.9, "currency": "BRL"}}}]},
                        }
                    ]
                }
            }
            with patch.object(self.service.amazon_client, "get_items", return_value=mocked_items):
                self.service.register_product("123", f"https://www.amazon.com.br/dp/652810196{index}")

        mocked_items = {
            "itemsResult": {
                "items": [
                    {
                        "detailPageURL": "https://www.amazon.com.br/dp/9999999999",
                        "itemInfo": {"title": {"displayValue": "Livro extra"}},
                        "images": {"primary": {"large": {"url": "https://img.test"}}},
                        "offersV2": {"listings": [{"price": {"money": {"amount": 29.9, "currency": "BRL"}}}]},
                    }
                ]
            }
        }
        with patch.object(self.service.amazon_client, "get_items", return_value=mocked_items):
            product, message = self.service.register_product("123", "https://www.amazon.com.br/dp/9999999999")

        self.assertIsNone(product)
        self.assertEqual(message, "Você já atingiu o limite de 5 produtos monitorados. Remova um produto para cadastrar outro. Use o comando /remover")

    def test_register_product_respects_configurable_limit(self) -> None:
        with patch.object(settings, "USER_PRODUCT_MONITOR_LIMIT", 2):
            for index in range(2):
                mocked_items = {
                    "itemsResult": {
                        "items": [
                            {
                                "detailPageURL": f"https://www.amazon.com.br/dp/652810190{index}",
                                "itemInfo": {"title": {"displayValue": f"Livro Config {index}"}},
                                "images": {"primary": {"large": {"url": "https://img.test"}}},
                                "offersV2": {"listings": [{"price": {"money": {"amount": 39.9, "currency": "BRL"}}}]},
                            }
                        ]
                    }
                }
                with patch.object(self.service.amazon_client, "get_items", return_value=mocked_items):
                    self.service.register_product("123", f"https://www.amazon.com.br/dp/652810190{index}")

            mocked_items = {
                "itemsResult": {
                    "items": [
                        {
                            "detailPageURL": "https://www.amazon.com.br/dp/6528101999",
                            "itemInfo": {"title": {"displayValue": "Livro Config Extra"}},
                            "images": {"primary": {"large": {"url": "https://img.test"}}},
                            "offersV2": {"listings": [{"price": {"money": {"amount": 29.9, "currency": "BRL"}}}]},
                        }
                    ]
                }
            }
            with patch.object(self.service.amazon_client, "get_items", return_value=mocked_items):
                product, message = self.service.register_product("123", "https://www.amazon.com.br/dp/6528101999")

        self.assertIsNone(product)
        self.assertEqual(message, "Você já atingiu o limite de 2 produtos monitorados. Remova um produto para cadastrar outro. Use o comando /remover")

    def test_register_product_accepts_book_titles_without_book_keywords(self) -> None:
        mocked_items = {
            "itemsResult": {
                "items": [
                    {
                        "detailPageURL": "https://www.amazon.com.br/dp/6555653302",
                        "itemInfo": {"title": {"displayValue": "A hipótese do amor"}},
                        "images": {"primary": {"large": {"url": "https://img.test"}}},
                        "offersV2": {"listings": [{"price": {"money": {"amount": 44.85, "currency": "BRL"}}}]},
                    }
                ]
            }
        }
        with patch.object(self.service.amazon_client, "get_items", return_value=mocked_items):
            product, message = self.service.register_product("123", "https://www.amazon.com.br/dp/6555653302")

        self.assertIsNotNone(product)
        self.assertEqual(message, "Produto cadastrado com sucesso.")

    def test_register_product_accepts_items_with_isbn(self) -> None:
        mocked_items = {
            "itemsResult": {
                "items": [
                    {
                        "detailPageURL": "https://www.amazon.com.br/dp/6555653302",
                        "itemInfo": {
                            "title": {"displayValue": "Livro Teste"},
                            "externalIds": {"ISBN13": [{"value": "9788532521496"}]},
                        },
                        "images": {"primary": {"large": {"url": "https://img.test"}}},
                        "offersV2": {"listings": [{"price": {"money": {"amount": 49.9, "currency": "BRL"}}}]},
                    }
                ]
            }
        }
        with patch.object(self.service.amazon_client, "get_items", return_value=mocked_items):
            product, message = self.service.register_product("123", "https://www.amazon.com.br/dp/6555653302")

        self.assertIsNotNone(product)
        self.assertEqual(message, "Produto cadastrado com sucesso.")

    def test_register_same_link_repeatedly_does_not_duplicate_relation(self) -> None:
        mocked_items = {
            "itemsResult": {
                "items": [
                    {
                        "detailPageURL": "https://www.amazon.com.br/dp/6555653302",
                        "itemInfo": {"title": {"displayValue": "A hipótese do amor"}},
                        "images": {"primary": {"large": {"url": "https://img.test"}}},
                        "offersV2": {"listings": [{"price": {"money": {"amount": 44.85, "currency": "BRL"}}}]},
                    }
                ]
            }
        }
        messages = []
        with patch.object(self.service.amazon_client, "get_items", return_value=mocked_items):
            for _ in range(5):
                _, message = self.service.register_product("123", "https://www.amazon.com.br/dp/6555653302")
                messages.append(message)

        self.assertEqual(messages[0], "Produto cadastrado com sucesso.")
        self.assertEqual(set(messages[1:]), {"Você já está monitorando este livro."})
        self.assertEqual(self.service.db.query(UserProduct).count(), 1)

    def test_unique_constraint_blocks_duplicate_relation_and_service_recovers(self) -> None:
        product = Product(asin="RACE1", title="Livro")
        user = User(telegram_id="123", username="u")
        self.service.db.add_all([product, user])
        self.service.db.commit()
        self.service.db.add(UserProduct(user_id=user.id, product_id=product.id))
        self.service.db.commit()

        self.service.db.add(UserProduct(user_id=user.id, product_id=product.id))
        from sqlalchemy.exc import IntegrityError
        with self.assertRaises(IntegrityError):
            self.service.db.commit()
        self.service.db.rollback()
        self.assertEqual(self.service.db.query(UserProduct).count(), 1)
    def test_list_products_returns_products_for_user(self) -> None:
        mocked_items = {
            "itemsResult": {
                "items": [
                    {
                        "detailPageURL": "https://example.com",
                        "itemInfo": {"title": {"displayValue": "Livro Teste"}},
                        "images": {"primary": {"large": {"url": "https://img.test"}}},
                    }
                ]
            }
        }
        with patch.object(self.service.amazon_client, "get_items", return_value=mocked_items):
            self.service.register_product("123", "https://www.amazon.com.br/dp/6528101965")

        products = self.service.list_products("123")

        self.assertEqual(len(products), 1)
        self.assertEqual(products[0].asin, "6528101965")

    def test_remove_product_by_index_removes_relation(self) -> None:
        mocked_items = {
            "itemsResult": {
                "items": [
                    {
                        "detailPageURL": "https://example.com",
                        "itemInfo": {"title": {"displayValue": "Livro Teste"}},
                        "images": {"primary": {"large": {"url": "https://img.test"}}},
                    }
                ]
            }
        }
        with patch.object(self.service.amazon_client, "get_items", return_value=mocked_items):
            self.service.register_product("123", "https://www.amazon.com.br/dp/6528101965")

        removed, message = self.service.remove_product("123", "1")

        self.assertTrue(removed)
        self.assertEqual(message, "Livro removido da sua lista.")
        self.assertEqual(self.session.query(UserProduct).count(), 0)


if __name__ == "__main__":
    unittest.main()
