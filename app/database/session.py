from __future__ import annotations

import re
from datetime import timedelta

import psycopg
from sqlalchemy import create_engine
from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.database.base import Base
from app.models.notification_queue import NotificationQueue
from app.models.price_history import PriceHistory
from app.utils.datetime_utc import utc_now

DATABASE_URL = settings.DATABASE_URL or "sqlite:///./book_price_bot.db"
if DATABASE_URL and DATABASE_URL.startswith("postgresql://") and "+psycopg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
elif DATABASE_URL and DATABASE_URL.startswith("postgresql+psycopg2://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)


def _is_sqlite_url(url: str) -> bool:
    return url.startswith("sqlite")


engine_kwargs: dict = {"future": True}
if _is_sqlite_url(DATABASE_URL):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_pre_ping"] = True

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_session():
    """Retorna uma sessão de banco de dados."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def cleanup_old_records(db: Session, max_days: int = 60) -> dict[str, int]:
    """Remove registros antigos dos históricos e filas persistentes."""
    from app.models.monitoring_queue import MonitoringQueue

    cutoff = utc_now() - timedelta(days=max_days)
    deleted = {
        "price_history": db.query(PriceHistory).filter(PriceHistory.checked_at < cutoff).delete(synchronize_session=False),
        "monitoring_queue": db.query(MonitoringQueue).filter(MonitoringQueue.created_at < cutoff).delete(synchronize_session=False),
        "notification_queue": db.query(NotificationQueue).filter(
            NotificationQueue.created_at < cutoff,
            NotificationQueue.status.in_(["sent", "failed", "skipped"]),
        ).delete(synchronize_session=False),
    }
    db.commit()
    return deleted


def init_db() -> None:
    """Prepara o banco com criação, ajustes e limpeza de dados antigos."""

    import app.models  # noqa: F401

    try:
        Base.metadata.create_all(bind=engine)
        _ensure_schema()
        with SessionLocal() as db:
            cleanup_old_records(db)
    except OperationalError as exc:
        if _is_missing_postgres_database_error(exc):
            _create_missing_postgres_database()
            Base.metadata.create_all(bind=engine)
            _ensure_schema()
            with SessionLocal() as db:
                cleanup_old_records(db)
            return
        raise


def _is_missing_postgres_database_error(error: OperationalError) -> bool:
    if not DATABASE_URL.startswith("postgresql"):
        return False

    message = str(error).lower()
    return bool(re.search(r"database .* does not exist|banco de dados .* nao existe|banco de dados .* não existe", message))


def _create_missing_postgres_database() -> None:
    url = make_url(DATABASE_URL)
    target_database = url.database
    if not target_database:
        raise RuntimeError("DATABASE_URL sem nome de banco para criação automática")

    admin_database = "postgres"
    admin_url = url.set(database=admin_database)
    admin_conninfo = str(admin_url).replace("postgresql+psycopg://", "postgresql://", 1)

    try:
        with psycopg.connect(admin_conninfo, autocommit=True) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target_database,))
                exists = cursor.fetchone() is not None
                if exists:
                    return
                cursor.execute(f'CREATE DATABASE "{target_database}"')
    except Exception as exc:
        raise RuntimeError(
            "Falha ao criar automaticamente o banco PostgreSQL ausente. "
            "Verifique permissões do usuário e DATABASE_URL."
        ) from exc


def _ensure_schema() -> None:
    inspector = inspect(engine)
    with engine.begin() as connection:
        existing_tables = set(inspector.get_table_names())

        if "monitoring_queue" in existing_tables:
            existing_columns = {column["name"] for column in inspector.get_columns("monitoring_queue")}
            if "available_at" not in existing_columns:
                _add_datetime_column(connection, "monitoring_queue", "available_at")
                connection.exec_driver_sql("UPDATE monitoring_queue SET available_at = CURRENT_TIMESTAMP WHERE available_at IS NULL")
            if "updated_at" not in existing_columns:
                _add_datetime_column(connection, "monitoring_queue", "updated_at")
                connection.exec_driver_sql("UPDATE monitoring_queue SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL")

        if "notification_queue" in existing_tables:
            existing_columns = {column["name"] for column in inspector.get_columns("notification_queue")}
            if "available_at" not in existing_columns:
                _add_datetime_column(connection, "notification_queue", "available_at")
                connection.exec_driver_sql("UPDATE notification_queue SET available_at = CURRENT_TIMESTAMP WHERE available_at IS NULL")
            if "updated_at" not in existing_columns:
                _add_datetime_column(connection, "notification_queue", "updated_at")
                connection.exec_driver_sql("UPDATE notification_queue SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL")


def _add_datetime_column(connection, table_name: str, column_name: str) -> None:
    if _is_sqlite_url(DATABASE_URL):
        connection.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {column_name} DATETIME")
        return

    connection.exec_driver_sql(
        f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} TIMESTAMP WITH TIME ZONE"
    )
