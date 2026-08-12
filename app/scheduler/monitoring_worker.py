from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.database.session import SessionLocal, init_db
from app.scheduler.worker import MonitoringWorker


def run_monitoring_worker_once() -> list[dict]:
    init_db()
    return MonitoringWorker(SessionLocal).drain_pending()


def run_monitoring_worker_forever() -> None:
    init_db()
    MonitoringWorker(SessionLocal).run_forever()


if __name__ == "__main__":
    if os.getenv("MONITORING_WORKER_MODE", "once").strip().lower() == "forever":
        run_monitoring_worker_forever()
    else:
        results = run_monitoring_worker_once()
        print(f"Monitoring worker processou {len(results)} item(ns).")
        for result in results:
            print(result)