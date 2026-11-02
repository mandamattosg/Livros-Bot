from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Callable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.amazon.usage import REPORT_TIMEZONE, record_creator_api_request
from app.config import settings
from app.database.session import SessionLocal
from app.logging import get_logger
from app.models.amazon_api_usage_daily import AmazonApiUsageDaily
from app.models.monitoring_queue import MonitoringQueue
from app.models.user_product import UserProduct
from app.services.admin_alert_service import send_admin_alert
from app.utils.datetime_utc import utc_now

logger = get_logger("app.services.amazon_api_usage_service")


def _previous_report_date(now: datetime | None = None) -> date:
    timestamp = now or datetime.now(REPORT_TIMEZONE)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=REPORT_TIMEZONE)
    return timestamp.astimezone(REPORT_TIMEZONE).date() - timedelta(days=1)


def get_daily_verification_stats(db: Session, day: date) -> dict[str, int]:
    """Conta as verificações do dia em São Paulo, classificando os produtos pelo número atual de monitores."""

    start = datetime.combine(day, time.min, REPORT_TIMEZONE).astimezone(timezone.utc)
    end = start + timedelta(days=1)

    monitor_count_subquery = (
        db.query(
            UserProduct.product_id.label("product_id"),
            func.count(UserProduct.id).label("monitor_count"),
        )
        .group_by(UserProduct.product_id)
        .subquery()
    )
    rows = (
        db.query(
            func.count(MonitoringQueue.id),
            func.coalesce(monitor_count_subquery.c.monitor_count, 0),
        )
        .outerjoin(monitor_count_subquery, monitor_count_subquery.c.product_id == MonitoringQueue.product_id)
        .filter(
            # Itens "skipped" são descartados pelo worker sem consultar a Amazon.
            MonitoringQueue.status.in_(["completed", "failed"]),
            MonitoringQueue.processed_at >= start,
            MonitoringQueue.processed_at < end,
        )
        .group_by(MonitoringQueue.product_id, monitor_count_subquery.c.monitor_count)
        .all()
    )

    high_monitor_min_users = max(settings.REFRESH_HIGH_MONITOR_MIN_USERS, 1)
    stats = {"hot_products": 0, "hot_verifications": 0, "cold_products": 0, "cold_verifications": 0}
    for verifications, monitor_count in rows:
        group = "hot" if monitor_count >= high_monitor_min_users else "cold"
        stats[f"{group}_products"] += 1
        stats[f"{group}_verifications"] += verifications

    return stats


def _format_verification_group(products: int, verifications: int) -> str:
    product_label = "produto" if products == 1 else "produtos"
    verification_label = "verificação" if verifications == 1 else "verificações"
    summary = f"{products} {product_label}, {verifications} {verification_label}"
    if not products:
        return summary

    average = f"{round(verifications / products, 1):g}".replace(".", ",")
    return f"{summary} (média de {average}x por produto)"


def build_daily_amazon_usage_report(usage: AmazonApiUsageDaily, verification_stats: dict[str, int]) -> str:
    total_verifications = verification_stats["hot_verifications"] + verification_stats["cold_verifications"]
    hot_summary = _format_verification_group(
        verification_stats["hot_products"],
        verification_stats["hot_verifications"],
    )
    cold_summary = _format_verification_group(
        verification_stats["cold_products"],
        verification_stats["cold_verifications"],
    )

    return (
        "📊 Relatório diário de uso da Amazon Creators API\n\n"
        f"📅 Data: {usage.usage_date:%d/%m/%Y} (horário de Brasília)\n"
        f"📨 Requisições tentadas: {usage.total_requests}\n"
        f"✅ Respostas bem-sucedidas: {usage.successful_requests}\n"
        f"🚦 Limite atingido (HTTP 429): {usage.rate_limited_requests}\n"
        f"❌ Outras falhas: {usage.failed_requests}\n\n"
        f"🔎 Verificações de preço: {total_verifications}\n"
        f"🔥 Quentes: {hot_summary}\n"
        f"❄️ Frios: {cold_summary}"
    )


def send_daily_amazon_usage_report(
    *,
    report_date: date | None = None,
    session_factory: Callable[[], Session] = SessionLocal,
    alert_sender: Callable[[str], bool] = send_admin_alert,
) -> bool:
    """Send the previous São Paulo calendar day's request totals once."""

    day = report_date or _previous_report_date()
    db = session_factory()
    try:
        usage = db.get(AmazonApiUsageDaily, day)
        if usage is None:
            usage = AmazonApiUsageDaily(usage_date=day)
            db.add(usage)
            db.commit()
            db.refresh(usage)

        if usage.report_sent_at is not None:
            logger.info("Relatório de uso da Amazon de %s já foi enviado.", day)
            return False

        report = build_daily_amazon_usage_report(usage, get_daily_verification_stats(db, day))
        if not alert_sender(report):
            logger.warning("Falha ao enviar o relatório diário de uso da Amazon referente a %s.", day)
            return False

        usage.report_sent_at = utc_now()
        db.commit()
        return True
    finally:
        db.close()
