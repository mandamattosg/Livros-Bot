from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.admin_alert_service import send_admin_alert


def _format_brl(value: float) -> str:
    formatted = f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {formatted}"


def _format_promotion(result: dict[str, Any]) -> str:
    asin = result.get("asin") or f"produto #{result.get('product_id', '?')}"
    title = " ".join(str(result.get("title") or "").split())
    if title and title != asin:
        if len(title) > 55:
            title = f"{title[:52]}..."
        product_label = f"{asin} — {title}"
    else:
        product_label = str(asin)

    previous_price = result.get("previous_price")
    current_price = result.get("price")
    drop_amount = result.get("drop_amount")
    drop_percentage = result.get("drop_percentage")
    if previous_price is not None and current_price is not None:
        if drop_amount is None:
            drop_amount = previous_price - current_price
        reduction = f"−{_format_brl(float(drop_amount))}"
        if drop_percentage is not None:
            percentage_text = f"{float(drop_percentage):.2f}".replace(".", ",")
            reduction += f"; −{percentage_text}%"
        return (
            f"🔥 {product_label}: {_format_brl(float(previous_price))} → "
            f"{_format_brl(float(current_price))} ({reduction}) | "
            f"{result.get('notifications_queued', 0)} alertas"
        )
    return f"🔥 {product_label}: promoção detectada; preço atual indisponível"


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
        f"📦 Produtos verificados: {total_jobs} (1 produto por job)\n"
        f"✅ Jobs bem-sucedidos: {successful_jobs}\n"
        f"❌ Jobs falhados: {failed_jobs}\n"
        f"⏭️ Jobs pulados: {skipped_jobs}\n"
    )

    if drop_detected_count > 0:
        message += (
            f"\n🔥 Promoções detectadas: {drop_detected_count}\n"
            f"📬 Alertas enfileirados para usuários: {total_notifications}\n"
        )
    else:
        message += "\n❄️ Nenhuma promoção detectada nesta execução.\n"

    promotions = [result for result in results if result.get("drop_detected", False)]
    if promotions:
        message += "\n🔥 Detalhe das promoções:\n"
        omitted_promotions = 0
        for result in promotions:
            detail = _format_promotion(result)
            if len(message) + len(detail) + 1 > 3900:
                omitted_promotions += 1
                continue
            message += f"\n{detail}"
        if omitted_promotions:
            message += f"\n… {omitted_promotions} promoção(ões) omitida(s) do detalhamento por limite de tamanho."

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
