from __future__ import annotations

from app.database.session import init_db
from app.logging import get_logger
from app.services.amazon_api_usage_service import send_daily_amazon_usage_report

logger = get_logger("app.scheduler.amazon_usage_report")


def main() -> None:
    init_db()
    sent = send_daily_amazon_usage_report()
    if sent:
        logger.info("Relatório diário de uso da Amazon enviado ao admin.")
    else:
        logger.info("Relatório diário de uso da Amazon não enviado (já enviado ou falha no destino).")


if __name__ == "__main__":
    main()
