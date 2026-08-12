from __future__ import annotations

import os
import statistics
import time

from app.amazon.client import AmazonAuthenticationError, AmazonClient, AmazonRateLimitError


TOTAL_PRODUCTS = 4000
BATCH_SIZE = 10
REQUEST_DELAY_SECONDS = float(os.getenv("AMAZON_LOAD_REQUEST_DELAY", "0.20"))
STOP_ON_AUTH_ERROR = os.getenv("AMAZON_LOAD_STOP_ON_AUTH_ERROR", "true").strip().lower() == "true"


def _generate_asins(total: int) -> list[str]:
    # Sintaticamente válidos (10 chars) para exercitar o volume de chamadas.
    return [f"B{index:09d}" for index in range(1, total + 1)]


def _chunk(items: list[str], size: int) -> list[list[str]]:
    return [items[index:index + size] for index in range(0, len(items), size)]


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * p
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    fraction = rank - low
    return ordered[low] + (ordered[high] - ordered[low]) * fraction


def main() -> None:
    client = AmazonClient()
    asins = _generate_asins(TOTAL_PRODUCTS)
    batches = _chunk(asins, BATCH_SIZE)

    success = 0
    rate_limited = 0
    auth_errors = 0
    other_errors = 0
    total_items_returned = 0
    latencies_ms: list[float] = []

    test_start = time.perf_counter()

    for index, batch in enumerate(batches, start=1):
        started = time.perf_counter()
        try:
            response = client.get_items(batch)
            elapsed_ms = (time.perf_counter() - started) * 1000
            latencies_ms.append(elapsed_ms)

            items = response.get("itemsResult", {}).get("items", [])
            total_items_returned += len(items)
            success += 1
        except AmazonRateLimitError:
            elapsed_ms = (time.perf_counter() - started) * 1000
            latencies_ms.append(elapsed_ms)
            rate_limited += 1
        except AmazonAuthenticationError:
            elapsed_ms = (time.perf_counter() - started) * 1000
            latencies_ms.append(elapsed_ms)
            auth_errors += 1
            if STOP_ON_AUTH_ERROR:
                print("Abortando por erro de autenticação.")
                break
        except Exception as exc:  # pragma: no cover - script operacional
            elapsed_ms = (time.perf_counter() - started) * 1000
            latencies_ms.append(elapsed_ms)
            other_errors += 1
            print(f"Erro no lote {index}/{len(batches)}: {exc}")

        if REQUEST_DELAY_SECONDS > 0:
            time.sleep(REQUEST_DELAY_SECONDS)

    total_seconds = time.perf_counter() - test_start
    processed = success + rate_limited + auth_errors + other_errors
    req_per_sec = (processed / total_seconds) if total_seconds > 0 else 0.0

    print("=== AMAZON REAL REQUEST LOAD TEST ===")
    print(f"target_products={TOTAL_PRODUCTS}")
    print(f"batch_size={BATCH_SIZE}")
    print(f"target_requests={len(batches)}")
    print(f"request_delay_seconds={REQUEST_DELAY_SECONDS}")
    print(f"processed_requests={processed}")
    print(f"success_requests={success}")
    print(f"rate_limited_requests={rate_limited}")
    print(f"auth_error_requests={auth_errors}")
    print(f"other_error_requests={other_errors}")
    print(f"returned_items_total={total_items_returned}")
    print(f"total_seconds={total_seconds:.2f}")
    print(f"throughput_req_per_sec={req_per_sec:.2f}")

    if latencies_ms:
        print(f"latency_avg_ms={statistics.mean(latencies_ms):.2f}")
        print(f"latency_p50_ms={_percentile(latencies_ms, 0.50):.2f}")
        print(f"latency_p95_ms={_percentile(latencies_ms, 0.95):.2f}")
        print(f"latency_max_ms={max(latencies_ms):.2f}")

    if success == len(batches):
        print("RESULT=PASS")
    else:
        print("RESULT=PARTIAL")


if __name__ == "__main__":
    main()