from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app.amazon.usage import REPORT_TIMEZONE, record_creator_api_request
from app.database.session import SessionLocal
from app.logging import get_logger
from app.models.amazon_api_usage_daily import AmazonApiUsageDaily
from app.services.admin_alert_service import send_admin_alert
from app.utils.datetime_utc import utc_now

logger = get_logger("app.services.amazon_api_usage_service")


def _previous_report_date(now: datetime | None = None) -> date:
    timestamp = now or datetime.now(REPORT_TIMEZONE)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=REPORT_TIMEZONE)
    return timestamp.astimezone(REPORT_TIMEZONE).date() - timedelta(days=1)


def build_daily_amazon_usage_report(usage: AmazonApiUsageDaily) -> str:
    return (
        "📊 Relatório diário de uso da Amazon Creators API\n\n"
        f"📅 Data: {usage.usage_date:%d/%m/%Y} (horário de Brasília)\n"
        f"📨 Requisições tentadas: {usage.total_requests}\n"
        f"✅ Respostas bem-sucedidas: {usage.successful_requests}\n"
        f"🚦 Limite atingido (HTTP 429): {usage.rate_limited_requests}\n"
        f"❌ Outras falhas: {usage.failed_requests}"
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

        if not alert_sender(build_daily_amazon_usage_report(usage)):
            logger.error("Falha ao enviar o relatório diário de uso da Amazon referente a %s.", day)
            return False

        usage.report_sent_at = utc_now()
        db.commit()
        return True
    finally:
        db.close()
