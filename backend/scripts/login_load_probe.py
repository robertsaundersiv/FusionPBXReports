"""Concurrent login load probe for quick auth endpoint benchmarking."""

import argparse
import asyncio
import os
import statistics
import time
from typing import Dict, List

import aiohttp


def percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int((len(ordered) - 1) * p)
    return ordered[index]


async def one_login(session: aiohttp.ClientSession, url: str, username: str, password: str) -> Dict[str, float | int | str]:
    start = time.perf_counter()
    try:
        async with session.post(url, params={"username": username, "password": password}) as resp:
            await resp.text()
            elapsed_ms = (time.perf_counter() - start) * 1000
            return {"status": resp.status, "elapsed_ms": elapsed_ms}
    except Exception as exc:  # pragma: no cover - diagnostic script
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {"status": "error", "elapsed_ms": elapsed_ms, "error": str(exc)}


async def run_probe(base_url: str, username: str, password: str, requests_count: int, concurrency: int) -> None:
    endpoint = f"{base_url.rstrip('/')}/api/v1/auth/login"
    timeout = aiohttp.ClientTimeout(total=30)
    connector = aiohttp.TCPConnector(limit=max(concurrency * 2, 20))

    statuses: Dict[str, int] = {}
    durations: List[float] = []

    sem = asyncio.Semaphore(concurrency)

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        async def bounded_call() -> None:
            async with sem:
                result = await one_login(session, endpoint, username, password)
                status_key = str(result["status"])
                statuses[status_key] = statuses.get(status_key, 0) + 1
                durations.append(float(result["elapsed_ms"]))

        started = time.perf_counter()
        await asyncio.gather(*(bounded_call() for _ in range(requests_count)))
        total_s = time.perf_counter() - started

    success = statuses.get("200", 0)
    failures = requests_count - success

    print("=== Login Load Probe ===")
    print(f"Endpoint: {endpoint}")
    print(f"Requests: {requests_count}")
    print(f"Concurrency: {concurrency}")
    print(f"Total time (s): {total_s:.2f}")
    print(f"Throughput (req/s): {(requests_count / total_s):.2f}" if total_s else "Throughput (req/s): 0")
    print(f"Status counts: {statuses}")
    print(f"Success: {success}  Failures: {failures}")

    if durations:
        print(f"Latency mean (ms): {statistics.mean(durations):.2f}")
        print(f"Latency p50 (ms): {percentile(durations, 0.50):.2f}")
        print(f"Latency p95 (ms): {percentile(durations, 0.95):.2f}")
        print(f"Latency p99 (ms): {percentile(durations, 0.99):.2f}")
        print(f"Latency max (ms): {max(durations):.2f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run concurrent login load probe")
    parser.add_argument("--base-url", default=os.getenv("LOGIN_PROBE_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--username", default=os.getenv("ADMIN_USERNAME", "admin"))
    parser.add_argument("--password", default=os.getenv("ADMIN_PASSWORD", "admin"))
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=25)
    args = parser.parse_args()

    asyncio.run(
        run_probe(
            base_url=args.base_url,
            username=args.username,
            password=args.password,
            requests_count=args.requests,
            concurrency=args.concurrency,
        )
    )
