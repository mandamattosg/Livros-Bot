from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.database.session import SessionLocal, init_db
from app.logging import get_logger
from app.scheduler.worker import MonitoringWorker

logger = get_logger("app.scheduler.monitoring_worker")


def run_monitoring_worker_once() -> list[dict]:
    logger.info("Iniciando monitoring worker em modo once; preparando banco de dados.")
    init_db()
    return MonitoringWorker(SessionLocal).drain_pending()


def run_monitoring_worker_forever() -> None:
    logger.info("Iniciando monitoring worker em modo forever; preparando banco de dados.")
    init_db()
    logger.info("Banco preparado; iniciando loop do monitoring worker.")
    MonitoringWorker(SessionLocal).run_forever()


if __name__ == "__main__":
    if os.getenv("MONITORING_WORKER_MODE", "once").strip().lower() == "forever":
        run_monitoring_worker_forever()
    else:
        results = run_monitoring_worker_once()
        logger.info("Monitoring worker processou %s item(ns).", len(results))
        for result in results:
            logger.info("Resultado do monitoring worker: %s", result)