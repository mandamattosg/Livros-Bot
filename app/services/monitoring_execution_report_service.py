from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.admin_alert_service import send_admin_alert


def build_monitoring_execution_report(
    results: list[dict[str, Any]],
    execution_time_seconds: float | None = None,
) -> str:
    """Constrói um relatório de execução do monitoring worker."""

    total_jobs = len(results)
    successful_jobs = sum(1 for r in results if r.get("status") == "updated")
    failed_jobs = sum(1 for r in results if r.get("status") not in ["updated", "missing_product", "skipped"])
    skipped_jobs = sum(1 for r in results if r.get("status") in ["missing_product", "skipped"])
    drop_detected_count = sum(1 for r in results if r.get("drop_detected", False))
    total_notifications = sum(r.get("notifications_queued", 0) for r in results)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    message = (
        "📊 Relatório de Execução - Monitoramento de Preços\n\n"
        f"⏰ Timestamp: {timestamp}\n"
        f"📦 Total de jobs processados: {total_jobs}\n"
        f"✅ Jobs bem-sucedidos: {successful_jobs}\n"
        f"❌ Jobs falhados: {failed_jobs}\n"
        f"⏭️ Jobs pulados: {skipped_jobs}\n"
    )

    if drop_detected_count > 0:
        message += (
            f"\n🔥 Promoções detectadas: {drop_detected_count}\n"
            f"📬 Alertas enviados aos usuários: {total_notifications}\n"
        )
    else:
        message += "\n❄️ Nenhuma promoção detectada nesta execução.\n"

    if execution_time_seconds is not None:
        message += f"\n⏱️ Tempo de execução: {execution_time_seconds:.2f}s"

    return message


def send_monitoring_execution_report(
    results: list[dict[str, Any]],
    execution_time_seconds: float | None = None,
) -> bool:
    """Envia um relatório de execução do monitoring worker para o admin."""

    if not results:
        return False

    report = build_monitoring_execution_report(results, execution_time_seconds)
    return send_admin_alert(report)
