from __future__ import annotations

from app.services.monitoring_execution_report_service import build_monitoring_execution_report


def test_build_monitoring_execution_report_with_drops():
    """Testa relatório quando promoções são detectadas."""
    results = [
        {
            "product_id": 1,
            "asin": "B001",
            "status": "updated",
            "price": 49.90,
            "drop_detected": True,
            "notifications_queued": 3,
        },
        {
            "product_id": 2,
            "asin": "B002",
            "status": "updated",
            "price": 29.90,
            "drop_detected": False,
            "notifications_queued": 0,
        },
        {
            "product_id": 3,
            "asin": "B003",
            "status": "updated",
            "price": 19.90,
            "drop_detected": True,
            "notifications_queued": 2,
        },
    ]

    report = build_monitoring_execution_report(results, execution_time_seconds=5.25)

    assert "Total de jobs processados: 3" in report
    assert "Jobs bem-sucedidos: 3" in report
    assert "Jobs falhados: 0" in report
    assert "Promoções detectadas: 2" in report
    assert "Alertas enviados aos usuários: 5" in report
    assert "Tempo de execução: 5.25s" in report
    assert "📊 Relatório de Execução" in report
    assert "🔥" in report  # Ícone de promoção


def test_build_monitoring_execution_report_without_drops():
    """Testa relatório quando nenhuma promoção é detectada."""
    results = [
        {
            "product_id": 1,
            "asin": "B001",
            "status": "updated",
            "price": 49.90,
            "drop_detected": False,
            "notifications_queued": 0,
        },
        {
            "product_id": 2,
            "asin": "B002",
            "status": "updated",
            "price": 29.90,
            "drop_detected": False,
            "notifications_queued": 0,
        },
    ]

    report = build_monitoring_execution_report(results, execution_time_seconds=2.15)

    assert "Total de jobs processados: 2" in report
    assert "Jobs bem-sucedidos: 2" in report
    assert "❄️ Nenhuma promoção detectada" in report
    assert "Tempo de execução: 2.15s" in report


def test_build_monitoring_execution_report_with_failures():
    """Testa relatório com jobs falhados."""
    results = [
        {
            "product_id": 1,
            "asin": "B001",
            "status": "updated",
            "price": 49.90,
            "drop_detected": False,
            "notifications_queued": 0,
        },
        {
            "product_id": 2,
            "asin": "B002",
            "status": "failed",
            "drop_detected": False,
            "notifications_queued": 0,
        },
        {
            "product_id": 3,
            "asin": None,
            "status": "missing_product",
            "drop_detected": False,
            "notifications_queued": 0,
        },
    ]

    report = build_monitoring_execution_report(results)

    assert "Total de jobs processados: 3" in report
    assert "Jobs bem-sucedidos: 1" in report
    assert "Jobs falhados: 1" in report
    assert "Jobs pulados: 1" in report
    assert "❌ Jobs falhados: 1" in report


def test_build_monitoring_execution_report_without_execution_time():
    """Testa que relatório funciona sem tempo de execução."""
    results = [
        {
            "product_id": 1,
            "asin": "B001",
            "status": "updated",
            "price": 49.90,
            "drop_detected": False,
            "notifications_queued": 0,
        },
    ]

    report = build_monitoring_execution_report(results)

    assert "Total de jobs processados: 1" in report
    assert "⏱️ Tempo de execução:" not in report
