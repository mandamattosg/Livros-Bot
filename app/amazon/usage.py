from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Callable

from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.logging import get_logger
from app.models.amazon_api_usage_daily import AmazonApiUsageDaily

logger = get_logger("app.amazon.usage")
REPORT_TIMEZONE = timezone(timedelta(hours=-3), "BRT")


def record_creator_api_request(
    status_code: int | None,
    *,
    occurred_at: datetime | None = None,
    session_factory: Callable[[], Session] = SessionLocal,
) -> None:
    """Record one attempted Creators API HTTP request; never interrupt the API flow."""

    timestamp = occurred_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=REPORT_TIMEZONE)
    usage_date = timestamp.astimezone(REPORT_TIMEZONE).date()
    successful = int(status_code is not None and 200 <= status_code < 300)
    rate_limited = int(status_code == 429)
    counters = {
        "total_requests": 1,
        "successful_requests": successful,
        "rate_limited_requests": rate_limited,
        "failed_requests": int(not successful and not rate_limited),
    }

    db = session_factory()
    try:
        dialect_name = db.get_bind().dialect.name
        table = AmazonApiUsageDaily.__table__
        values = {"usage_date": usage_date, **counters}

        if dialect_name == "postgresql":
            statement = postgresql_insert(AmazonApiUsageDaily).values(**values)
        elif dialect_name == "sqlite":
            statement = sqlite_insert(AmazonApiUsageDaily).values(**values)
        else:
            _record_with_generic_dialect(db, usage_date, counters)
            return

        statement = statement.on_conflict_do_update(
            index_elements=[table.c.usage_date],
            set_={
                column: table.c[column] + statement.excluded[column]
                for column in counters
            },
        )
        db.execute(statement)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Não foi possível registrar uma tentativa da Creators API nas métricas diárias.")
    finally:
        db.close()


def _record_with_generic_dialect(db: Session, usage_date: date, counters: dict[str, int]) -> None:
    row = db.get(AmazonApiUsageDaily, usage_date)
    if row is None:
        row = AmazonApiUsageDaily(usage_date=usage_date, **counters)
        db.add(row)
    else:
        for column, increment in counters.items():
            setattr(row, column, getattr(row, column) + increment)
    db.commit()
