from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.monitoring_queue import MonitoringQueue
from app.models.notification_queue import NotificationQueue
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.models.registration_failure import REASON_LABELS, RegistrationFailure
from app.models.user import User
from app.models.user_product import UserProduct
from app.utils.datetime_utc import utc_now

REGISTRATION_FAILURE_WINDOW_DAYS = 7


def _build_registration_failures_text(stats: dict[str, object]) -> str:
    total = int(stats.get("registration_failures") or 0)
    lines = [f"❌ Cadastros com falha ({REGISTRATION_FAILURE_WINDOW_DAYS} dias): {total}"]
    if total:
        by_reason = stats.get("registration_failures_by_reason") or {}
        for reason, label in REASON_LABELS.items():
            count = int(by_reason.get(reason) or 0)
            if count:
                lines.append(f"   • {label}: {count}")
        unrecovered = int(stats.get("registration_failure_users_without_product") or 0)
        lines.append(f"   👤 Usuários que falharam e seguem sem livro: {unrecovered}")
    return "\n".join(lines) + "\n"


def get_registration_failure_stats(db: Session, now: datetime | None = None) -> dict[str, object]:
    """Resume as falhas de cadastro da janela recente e quantos usuários não se recuperaram."""

    cutoff = (now or utc_now()) - timedelta(days=REGISTRATION_FAILURE_WINDOW_DAYS)
    rows = (
        db.query(RegistrationFailure.reason, func.count(RegistrationFailure.id))
        .filter(RegistrationFailure.created_at >= cutoff)
        .group_by(RegistrationFailure.reason)
        .all()
    )
    by_reason = {reason: int(count) for reason, count in rows}

    users_with_product = db.query(UserProduct.user_id).distinct()
    users_without_product = (
        db.query(func.count(func.distinct(RegistrationFailure.user_id)))
        .filter(
            RegistrationFailure.created_at >= cutoff,
            RegistrationFailure.user_id.isnot(None),
            RegistrationFailure.user_id.notin_(users_with_product),
        )
        .scalar()
        or 0
    )

    return {
        "registration_failures": sum(by_reason.values()),
        "registration_failures_by_reason": by_reason,
        "registration_failure_users_without_product": int(users_without_product),
    }


def build_admin_report_message(stats: dict[str, object]) -> str:
    top_product = str(stats.get("top_product") or "-")
    top_product_monitors = int(stats.get("top_product_monitors") or 0)
    last_price_update_at = stats.get("last_price_update_at")
    last_price_update_text = "-"
    if isinstance(last_price_update_at, datetime):
        last_price_update_text = last_price_update_at.strftime("%Y-%m-%d %H:%M:%S UTC")

    return (
        "📊 Relatório do Bot\n\n"
        f"👥 Usuários totais: {int(stats.get('total_users') or 0)}\n"
        f"✅ Usuários ativos (monitorando): {int(stats.get('active_users') or 0)}\n"
        f"📚 Produtos monitorados: {int(stats.get('products_monitored') or 0)}\n"
        f"🔥 Produtos quentes: {int(stats.get('hot_products') or 0)}\n"
        f"❄️ Produtos frios: {int(stats.get('cold_products') or 0)}\n"
        f"🏆 Produto mais monitorado: {top_product} ({top_product_monitors})\n"
        f"{_build_registration_failures_text(stats)}"
        f"🧭 Fila monitoramento pendente: {int(stats.get('pending_monitoring_jobs') or 0)}\n"
        f"📬 Fila notificação pendente: {int(stats.get('pending_notification_jobs') or 0)}\n"
        f"⏱️ Última atualização de preço: {last_price_update_text}"
    )


def get_product_temperature_counts(db: Session) -> dict[str, int]:
    """Conta produtos quentes e frios com o mesmo critério de frequência do refresh de preços."""

    high_monitor_min_users = max(settings.REFRESH_HIGH_MONITOR_MIN_USERS, 1)
    monitor_counts = db.query(func.count(UserProduct.id)).group_by(UserProduct.product_id).all()
    hot_products = sum(1 for (monitor_count,) in monitor_counts if monitor_count >= high_monitor_min_users)

    return {
        "hot_products": hot_products,
        "cold_products": len(monitor_counts) - hot_products,
    }


def get_admin_report_stats(db: Session) -> dict[str, object]:
    total_users = db.query(func.count(User.id)).scalar() or 0

    users_monitoring = (
        db.query(func.count(func.distinct(UserProduct.user_id)))
        .join(User, User.id == UserProduct.user_id)
        .filter(User.is_active.is_(True))
        .scalar()
        or 0
    )

    # No contexto do relatório operacional, consideramos "ativo" quem está
    # com ao menos um monitoramento vigente.
    active_users = users_monitoring

    products_monitored = db.query(func.count(func.distinct(UserProduct.product_id))).scalar() or 0
    total_monitorings = db.query(func.count(UserProduct.id)).scalar() or 0

    top_row = (
        db.query(
            Product.title,
            Product.asin,
            func.count(UserProduct.id).label("monitor_count"),
        )
        .join(UserProduct, UserProduct.product_id == Product.id)
        .group_by(Product.id, Product.title, Product.asin)
        .order_by(func.count(UserProduct.id).desc(), Product.id.asc())
        .first()
    )

    if top_row is None:
        top_product = "-"
        top_product_monitors = 0
    else:
        top_product = top_row.title or top_row.asin or "-"
        top_product_monitors = int(top_row.monitor_count or 0)

    pending_monitoring_jobs = (
        db.query(func.count(MonitoringQueue.id))
        .filter(MonitoringQueue.status.in_(["pending", "processing"]))
        .scalar()
        or 0
    )
    pending_notification_jobs = (
        db.query(func.count(NotificationQueue.id))
        .filter(NotificationQueue.status.in_(["pending", "sending"]))
        .scalar()
        or 0
    )

    last_price_update_at = db.query(func.max(PriceHistory.checked_at)).scalar()

    return {
        "total_users": int(total_users),
        "active_users": int(active_users),
        "users_monitoring": int(users_monitoring),
        "products_monitored": int(products_monitored),
        **get_product_temperature_counts(db),
        "total_monitorings": int(total_monitorings),
        "top_product": top_product,
        "top_product_monitors": int(top_product_monitors),
        "pending_monitoring_jobs": int(pending_monitoring_jobs),
        "pending_notification_jobs": int(pending_notification_jobs),
        "last_price_update_at": last_price_update_at,
        **get_registration_failure_stats(db),
    }
