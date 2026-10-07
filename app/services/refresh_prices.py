from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

from sqlalchemy import func

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.config import settings
from app.database.session import SessionLocal, init_db
from app.models.monitoring_queue import MonitoringQueue
from app.models.product import Product
from app.models.user_product import UserProduct
from app.scheduler.monitoring_queue import MonitoringQueueService
from app.utils.datetime_utc import ensure_utc, utc_now


def _select_products_for_refresh(db, now: datetime) -> tuple[list[Product], dict[str, int]]:
    monitor_count_subquery = (
        db.query(
            UserProduct.product_id.label("product_id"),
            func.count(UserProduct.id).label("monitor_count"),
        )
        .group_by(UserProduct.product_id)
        .subquery()
    )

    last_completed_subquery = (
        db.query(
            MonitoringQueue.product_id.label("product_id"),
            func.max(MonitoringQueue.processed_at).label("last_processed_at"),
        )
        .filter(MonitoringQueue.status == "completed")
        .group_by(MonitoringQueue.product_id)
        .subquery()
    )

    rows = (
        db.query(
            Product,
            func.coalesce(monitor_count_subquery.c.monitor_count, 0).label("monitor_count"),
            last_completed_subquery.c.last_processed_at,
        )
        .join(monitor_count_subquery, monitor_count_subquery.c.product_id == Product.id)
        .outerjoin(last_completed_subquery, last_completed_subquery.c.product_id == Product.id)
        .all()
    )

    high_monitor_min_users = max(settings.REFRESH_HIGH_MONITOR_MIN_USERS, 1)
    high_interval = timedelta(hours=max(settings.REFRESH_HIGH_MONITOR_INTERVAL_HOURS, 0))
    low_interval = timedelta(hours=max(settings.REFRESH_LOW_MONITOR_INTERVAL_HOURS, 0))
    # Absorve o drift entre o fim do ciclo anterior e o disparo do próximo gatilho.
    tolerance = timedelta(minutes=max(settings.REFRESH_INTERVAL_TOLERANCE_MINUTES, 0))

    eligible_products: list[Product] = []
    stats = {
        "products_found": len(rows),
        "high_frequency_products": 0,
        "low_frequency_products": 0,
        "eligible_high_frequency": 0,
        "eligible_low_frequency": 0,
    }

    for product, monitor_count, last_processed_at in rows:
        monitor_count_value = int(monitor_count or 0)
        is_high_frequency = monitor_count_value >= high_monitor_min_users
        if is_high_frequency:
            stats["high_frequency_products"] += 1
            interval = high_interval
            eligible_key = "eligible_high_frequency"
        else:
            stats["low_frequency_products"] += 1
            interval = low_interval
            eligible_key = "eligible_low_frequency"

        normalized_last_processed_at = ensure_utc(last_processed_at)
        # A zero interval bypasses the cooldown on every refresh execution.
        if (
            interval == timedelta(0)
            or normalized_last_processed_at is None
            or (normalized_last_processed_at + interval - tolerance) <= now
        ):
            eligible_products.append(product)
            stats[eligible_key] += 1

    return eligible_products, stats


def refresh_prices() -> dict[str, int]:
    init_db()
    db = SessionLocal()
    try:
        products, stats = _select_products_for_refresh(db, utc_now())
        if stats["products_found"] == 0:
            print("Nenhum produto cadastrado para atualizar.")
            return {"products_found": 0, "jobs_enqueued": 0}

        jobs_enqueued = MonitoringQueueService(db).enqueue_products(products)
        summary = {
            "products_found": stats["products_found"],
            "high_frequency_products": stats["high_frequency_products"],
            "low_frequency_products": stats["low_frequency_products"],
            "eligible_high_frequency": stats["eligible_high_frequency"],
            "eligible_low_frequency": stats["eligible_low_frequency"],
            "eligible_total": len(products),
            "jobs_enqueued": jobs_enqueued,
        }
        print(summary)
        return summary
    finally:
        db.close()


if __name__ == "__main__":
    refresh_prices()
