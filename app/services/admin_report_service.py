from __future__ import annotations

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.monitoring_queue import MonitoringQueue
from app.models.notification_queue import NotificationQueue
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.models.user import User
from app.models.user_product import UserProduct


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
        f"🏆 Produto mais monitorado: {top_product} ({top_product_monitors})\n"
        f"🧭 Fila monitoramento pendente: {int(stats.get('pending_monitoring_jobs') or 0)}\n"
        f"📬 Fila notificação pendente: {int(stats.get('pending_notification_jobs') or 0)}\n"
        f"⏱️ Última atualização de preço: {last_price_update_text}"
    )


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
        "total_monitorings": int(total_monitorings),
        "top_product": top_product,
        "top_product_monitors": int(top_product_monitors),
        "pending_monitoring_jobs": int(pending_monitoring_jobs),
        "pending_notification_jobs": int(pending_notification_jobs),
        "last_price_update_at": last_price_update_at,
    }
