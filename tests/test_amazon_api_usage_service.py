from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database.base import Base
from app.models.amazon_api_usage_daily import AmazonApiUsageDaily
from app.models.monitoring_queue import MonitoringQueue
from app.models.product import Product
from app.models.user import User
from app.models.user_product import UserProduct
from app.services.amazon_api_usage_service import (
    build_daily_amazon_usage_report,
    record_creator_api_request,
    send_daily_amazon_usage_report,
)


def test_record_creator_api_requests_counts_attempts_by_brasilia_date() -> None:
    engine = create_engine("sqlite:///:memory:")
    session_factory = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    try:
        # 02:59 UTC is 23:59 on the previous calendar day in São Paulo.
        timestamp = datetime(2026, 10, 2, 2, 59, tzinfo=timezone.utc)
        for status_code in (200, 429, 503, None):
            record_creator_api_request(
                status_code,
                occurred_at=timestamp,
                session_factory=session_factory,
            )

        with session_factory() as db:
            usage = db.get(AmazonApiUsageDaily, date(2026, 10, 1))
            assert usage is not None
            assert usage.total_requests == 4
            assert usage.successful_requests == 1
            assert usage.rate_limited_requests == 1
            assert usage.failed_requests == 2
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_daily_report_sends_totals_once() -> None:
    engine = create_engine("sqlite:///:memory:")
    session_factory = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    report_date = date(2026, 10, 1)
    try:
        record_creator_api_request(
            200,
            occurred_at=datetime(2026, 10, 1, 15, tzinfo=timezone.utc),
            session_factory=session_factory,
        )
        record_creator_api_request(
            429,
            occurred_at=datetime(2026, 10, 1, 15, tzinfo=timezone.utc),
            session_factory=session_factory,
        )
        captured_messages: list[str] = []

        def capture(message: str) -> bool:
            captured_messages.append(message)
            return True

        assert send_daily_amazon_usage_report(
            report_date=report_date,
            session_factory=session_factory,
            alert_sender=capture,
        )
        assert not send_daily_amazon_usage_report(
            report_date=report_date,
            session_factory=session_factory,
            alert_sender=capture,
        )

        assert len(captured_messages) == 1
        assert "01/10/2026" in captured_messages[0]
        assert "Requisições tentadas: 2" in captured_messages[0]
        assert "Respostas bem-sucedidas: 1" in captured_messages[0]
        assert "Limite atingido (HTTP 429): 1" in captured_messages[0]
        assert "Outras falhas: 0" in captured_messages[0]
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_daily_report_formats_zero_requests() -> None:
    usage = AmazonApiUsageDaily(
        usage_date=date(2026, 10, 1),
        total_requests=0,
        successful_requests=0,
        rate_limited_requests=0,
        failed_requests=0,
    )

    report = build_daily_amazon_usage_report(
        usage,
        {"hot_products": 0, "hot_verifications": 0, "cold_products": 0, "cold_verifications": 0},
    )

    assert "Requisições tentadas: 0" in report
    assert "Verificações de preço: 0" in report
    assert "Quentes: 0 produtos, 0 verificações\n" in report
    assert report.endswith("Frios: 0 produtos, 0 verificações")


def test_daily_report_includes_verifications_by_product_group() -> None:
    engine = create_engine("sqlite:///:memory:")
    session_factory = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    # O dia 01/10 em São Paulo vai de 03:00 UTC de 01/10 até 03:00 UTC de 02/10.
    first_moment = datetime(2026, 10, 1, 3, tzinfo=timezone.utc)
    last_moment = datetime(2026, 10, 2, 2, 59, tzinfo=timezone.utc)
    try:
        with session_factory() as db:
            users = [User(telegram_id=str(index)) for index in range(2)]
            products = [Product(asin=asin) for asin in ("HOT", "COLD1", "COLD2", "REMOVED")]
            db.add_all([*users, *products])
            db.flush()
            hot, cold_a, cold_b, removed = products
            db.add_all([
                UserProduct(user_id=users[0].id, product_id=hot.id),
                UserProduct(user_id=users[1].id, product_id=hot.id),
                UserProduct(user_id=users[0].id, product_id=cold_a.id),
                UserProduct(user_id=users[1].id, product_id=cold_b.id),
                MonitoringQueue(product_id=hot.id, status="completed", processed_at=first_moment),
                MonitoringQueue(product_id=hot.id, status="completed", processed_at=last_moment),
                MonitoringQueue(product_id=cold_a.id, status="completed", processed_at=first_moment),
                MonitoringQueue(product_id=cold_a.id, status="failed", processed_at=last_moment),
                MonitoringQueue(product_id=cold_b.id, status="completed", processed_at=first_moment),
                # Produto sem monitores hoje, mas verificado no dia do relatório.
                MonitoringQueue(product_id=removed.id, status="completed", processed_at=first_moment),
                # Nada abaixo deve entrar na contagem do dia.
                MonitoringQueue(product_id=hot.id, status="skipped", processed_at=first_moment),
                MonitoringQueue(product_id=hot.id, status="pending"),
                MonitoringQueue(
                    product_id=hot.id,
                    status="completed",
                    processed_at=first_moment - timedelta(minutes=1),
                ),
                MonitoringQueue(
                    product_id=hot.id,
                    status="completed",
                    processed_at=last_moment + timedelta(minutes=1),
                ),
            ])
            db.commit()

        captured_messages: list[str] = []

        def capture(message: str) -> bool:
            captured_messages.append(message)
            return True

        with patch.object(settings, "REFRESH_HIGH_MONITOR_MIN_USERS", 2):
            assert send_daily_amazon_usage_report(
                report_date=date(2026, 10, 1),
                session_factory=session_factory,
                alert_sender=capture,
            )

        assert "Verificações de preço: 6" in captured_messages[0]
        assert "Quentes: 1 produto, 2 verificações (média de 2x por produto)" in captured_messages[0]
        assert "Frios: 3 produtos, 4 verificações (média de 1,3x por produto)" in captured_messages[0]
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
