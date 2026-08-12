from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.monitoring_queue import MonitoringQueue
from app.models.notification_queue import NotificationQueue
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.models.user import User
from app.models.user_product import UserProduct
from app.scheduler.worker import MonitoringWorker


TOTAL_USERS = 4000
TOTAL_PRODUCTS = 4000
DROP_ALERTS = 30
BASE_PRICE = Decimal("100.00")
DROP_PRICE = Decimal("90.00")
NO_DROP_PRICE = Decimal("110.00")


def _asin_for(index: int) -> str:
    return f"ASIN{index:06d}"


def _index_from_asin(asin: str) -> int:
    return int(asin[-6:])


def _build_mock_item(asin: str) -> dict:
    index = _index_from_asin(asin)
    amount = float(DROP_PRICE if index < DROP_ALERTS else NO_DROP_PRICE)
    return {
        "asin": asin,
        "detailPageURL": f"https://www.amazon.com.br/dp/{asin}",
        "itemInfo": {"title": {"displayValue": f"Livro {index}"}},
        "offersV2": {"listings": [{"price": {"amount": amount, "currency": "BRL"}}]},
    }


def _fake_get_items(self, asins: list[str]) -> dict:  # noqa: ANN001
    return {"itemsResult": {"items": [_build_mock_item(asin) for asin in asins]}}


def main() -> None:
    db_path = Path("tmp_massive_load_test.db")
    engine = create_engine(f"sqlite:///{db_path}")
    Session = sessionmaker(bind=engine)

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    setup_start = perf_counter()
    session = Session()
    try:
        users = [User(telegram_id=str(index + 1), username=f"user_{index + 1}") for index in range(TOTAL_USERS)]
        products = [Product(asin=_asin_for(index), title=f"Livro {index}") for index in range(TOTAL_PRODUCTS)]
        session.add_all(users)
        session.add_all(products)
        session.flush()

        links = [
            UserProduct(user_id=users[index].id, product_id=products[index].id)
            for index in range(min(TOTAL_USERS, TOTAL_PRODUCTS))
        ]
        session.add_all(links)

        initial_history = [PriceHistory(product_id=product.id, price=BASE_PRICE) for product in products]
        session.add_all(initial_history)

        queue_items = [MonitoringQueue(product_id=product.id, status="pending") for product in products]
        session.add_all(queue_items)

        session.commit()
    finally:
        session.close()
    setup_seconds = perf_counter() - setup_start

    execution_start = perf_counter()
    with patch("app.amazon.client.AmazonClient.get_items", new=_fake_get_items):
        worker = MonitoringWorker(Session, batch_size=200)
        results = worker.drain_pending()
    execution_seconds = perf_counter() - execution_start

    session = Session()
    try:
        completed_count = session.query(func.count(MonitoringQueue.id)).filter(MonitoringQueue.status == "completed").scalar() or 0
        queued_notifications = session.query(func.count(NotificationQueue.id)).scalar() or 0
        total_price_history = session.query(func.count(PriceHistory.id)).scalar() or 0
    finally:
        session.close()

    drop_detected = sum(1 for result in results if result.get("drop_detected"))
    total_notifications_reported = sum(int(result.get("notifications_queued", 0)) for result in results)

    print("=== MASSIVE LOAD TEST ===")
    print(f"users={TOTAL_USERS}")
    print(f"products={TOTAL_PRODUCTS}")
    print(f"target_drop_alerts={DROP_ALERTS}")
    print(f"setup_seconds={setup_seconds:.2f}")
    print(f"execution_seconds={execution_seconds:.2f}")
    print(f"processed_results={len(results)}")
    print(f"completed_queue_items={completed_count}")
    print(f"drop_detected={drop_detected}")
    print(f"notifications_reported_by_worker={total_notifications_reported}")
    print(f"notifications_rows_in_db={queued_notifications}")
    print(f"price_history_rows={total_price_history}")

    if len(results) != TOTAL_PRODUCTS:
        raise AssertionError(f"Esperado processar {TOTAL_PRODUCTS} itens, mas processou {len(results)}")
    if completed_count != TOTAL_PRODUCTS:
        raise AssertionError(f"Esperado {TOTAL_PRODUCTS} itens completados, mas encontrou {completed_count}")
    if drop_detected != DROP_ALERTS:
        raise AssertionError(f"Esperado {DROP_ALERTS} quedas, mas detectou {drop_detected}")
    if queued_notifications != DROP_ALERTS:
        raise AssertionError(f"Esperado {DROP_ALERTS} notificações, mas encontrou {queued_notifications}")
    if total_notifications_reported != DROP_ALERTS:
        raise AssertionError(
            f"Worker reportou {total_notifications_reported} notificações em fila, esperado {DROP_ALERTS}"
        )

    print("RESULT=PASS")


if __name__ == "__main__":
    main()