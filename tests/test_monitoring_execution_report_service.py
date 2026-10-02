from __future__ import annotations

from app.services.monitoring_execution_report_service import build_monitoring_execution_report


def test_build_monitoring_execution_report_with_drops():
    """Testa relatório quando promoções são detectadas."""
    results = [
        {
            "product_id": 1,
            "asin": "B001",
            "title": "Livro de exemplo",
            "status": "updated",
            "price": 49.90,
            "previous_price": 59.90,
            "drop_amount": 10.00,
            "drop_percentage": 16.69,
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
            "title": "Outro livro",
            "status": "updated",
            "price": 19.90,
            "previous_price": 25.00,
            "drop_amount": 5.10,
            "drop_percentage": 20.40,
            "drop_detected": True,
            "notifications_queued": 2,
        },
    ]

    report = build_monitoring_execution_report(results, execution_time_seconds=5.25)

    assert "Produtos verificados: 3 (1 produto por job)" in report
    assert "Jobs bem-sucedidos: 3" in report
    assert "Jobs falhados: 0" in report
    assert "Promoções detectadas: 2" in report
    assert "Alertas enfileirados para usuários: 5" in report
    assert "Tempo de execução: 5.25s" in report
    assert "📊 Relatório de Execução" in report
    assert "🔥" in report  # Ícone de promoção
    assert "📋 Resultado por produto" not in report
    assert "B002" not in report
    assert "B001 — Livro de exemplo: R$ 59,90 → R$ 49,90" in report
    assert "−R$ 10,00; −16,69%" in report
    assert "B003 — Outro livro: R$ 25,00 → R$ 19,90" in report


def test_build_monitoring_execution_report_without_drops():
    """Testa relatório quando nenhuma promoção é detectada."""
    results = [
        {
            "product_id": 1,
            "asin": "B001",
            "title": "Livro de exemplo",
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

    assert "Produtos verificados: 2 (1 produto por job)" in report
    assert "Jobs bem-sucedidos: 2" in report
    assert "❄️ Nenhuma promoção detectada" in report
    assert "Detalhe das promoções" not in report
    assert "B001" not in report
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

    assert "Produtos verificados: 3 (1 produto por job)" in report
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

    assert "Produtos verificados: 1 (1 produto por job)" in report
    assert "⏱️ Tempo de execução:" not in report
