"""100-ticket load test — measures P50/P95 end-to-end latency.

Usage::

    # With the backend running on :8000 and enterprise API on :8001:
    python tests/load_test.py

    # Or with explicit base URLs:
    NEURADESK_URL=http://localhost:8000 python tests/load_test.py

The script:
1. Preflight-checks the enterprise API on :8001 (exits loudly if down).
2. Registers a throw-away test user on the main API.
3. Submits 100 tickets with up to 10 concurrent workers.
4. Reports P50 / P95 / mean / min / max latency.
"""

import asyncio
import os
import statistics
import sys
import time
import uuid
from typing import Optional

import httpx

BASE_URL: str = os.environ.get("NEURADESK_URL", "http://localhost:8000")
ENTERPRISE_URL: str = os.environ.get("ENTERPRISE_URL", "http://localhost:8001")

TOTAL_TICKETS = 100
# SQLite and local Groq rate limits: 3 concurrent is stable locally.
# Increase to 10+ when running against PostgreSQL in Cloud Run.
CONCURRENCY = int(os.environ.get("LOAD_CONCURRENCY", "3"))

# 10 representative ticket texts cycled across the 100 submissions
TICKET_TEXTS = [
    "I forgot my corporate password and cannot log in.",
    "Please grant me read access to the marketing shared drive.",
    "I need to install VS Code on my MacBook — can IT approve this?",
    "I'd like to take annual leave from June 10 to June 14.",
    "Our production database is down — P1 incident, all engineers affected.",
    "My VPN disconnects every 20 minutes, making remote work impossible.",
    "Can someone reset the MFA token on my account? I lost my phone.",
    "I need access to the Salesforce sandbox environment for testing.",
    "Please install Docker Desktop on my Windows laptop.",
    "I want to report a phishing email I received this morning.",
]


# ── Preflight ─────────────────────────────────────────────────────────────────

def preflight_enterprise_api() -> None:
    """Check that the enterprise API is reachable before starting the load test.

    Exits with a clear error message if the service is not running, so the
    100-ticket run never silently fires against a missing service.
    """
    try:
        resp = httpx.get(f"{ENTERPRISE_URL}/openapi.json", timeout=5)
        resp.raise_for_status()
    except Exception:
        print(f"ERROR: enterprise API not running on {ENTERPRISE_URL}")
        print(
            "Start it with:\n"
            "  ENTERPRISE_API_SECRET=<secret> "
            "uvicorn services.enterprise_api:app --port 8001"
        )
        sys.exit(1)


# ── Auth ──────────────────────────────────────────────────────────────────────

def register_test_user(client: httpx.Client) -> str:
    """Register an ephemeral test user and return its JWT access token."""
    email = f"loadtest-{uuid.uuid4().hex[:8]}@neuradesk-test.example.com"
    password = "loadtest-pw-2026"
    resp = client.post(
        f"{BASE_URL}/auth/register",
        json={"email": email, "password": password},
    )
    if resp.status_code not in (200, 201):
        print(f"ERROR: failed to register test user — {resp.status_code} {resp.text}")
        sys.exit(1)
    token: str = resp.json()["access_token"]
    print(f"Registered test user {email}")
    return token


# ── Ticket submission ─────────────────────────────────────────────────────────

async def submit_ticket(
    client: httpx.AsyncClient,
    token: str,
    text: str,
    semaphore: asyncio.Semaphore,
) -> Optional[float]:
    """Submit one ticket and return its wall-clock latency in seconds."""
    async with semaphore:
        t0 = time.perf_counter()
        try:
            resp = await client.post(
                f"{BASE_URL}/tickets",
                json={"text": text},
                headers={"Authorization": f"Bearer {token}"},
                timeout=60,
            )
            elapsed = time.perf_counter() - t0
            if resp.status_code not in (200, 201):
                print(f"  WARN: ticket failed — {resp.status_code}")
                return None
            return elapsed
        except Exception as exc:
            print(f"  WARN: request error — {exc}")
            return None


async def run_load_test(token: str) -> list[float]:
    """Submit TOTAL_TICKETS tickets with up to CONCURRENCY concurrent workers.

    Sends one warmup ticket first (sequential) so the retriever singleton and
    model weights are fully loaded before concurrent requests race to use them.
    """
    semaphore = asyncio.Semaphore(CONCURRENCY)
    latencies: list[float] = []

    async with httpx.AsyncClient() as client:
        # Warmup: one sequential ticket forces the retriever + cross-encoder to
        # initialise. Without this, concurrent cold-start requests race on the
        # singleton and corrupt PyTorch's model-loading state.
        print("  Warming up retriever (1 ticket)…", flush=True)
        warmup = await submit_ticket(client, token, TICKET_TEXTS[0], asyncio.Semaphore(1))
        if warmup is None:
            print("ERROR: warmup ticket failed — check backend logs and exit")
            return []
        print(f"  Warmup OK ({warmup:.2f}s). Starting load…\n")

        tasks = [
            submit_ticket(
                client,
                token,
                TICKET_TEXTS[i % len(TICKET_TEXTS)],
                semaphore,
            )
            for i in range(TOTAL_TICKETS)
        ]

        print(
            f"Submitting {TOTAL_TICKETS} tickets "
            f"(concurrency={CONCURRENCY}, backend={BASE_URL})…\n"
        )
        t_start = time.perf_counter()
        results = await asyncio.gather(*tasks)
        total_wall = time.perf_counter() - t_start

        for r in results:
            if r is not None:
                latencies.append(r)

    print(f"\nCompleted in {total_wall:.1f}s — {len(latencies)}/{TOTAL_TICKETS} succeeded")
    return latencies


# ── Stats ─────────────────────────────────────────────────────────────────────

def report(latencies: list[float]) -> None:
    """Print a latency summary table to stdout."""
    if not latencies:
        print("ERROR: no successful tickets — nothing to report")
        return

    sorted_lat = sorted(latencies)
    n = len(sorted_lat)

    def percentile(p: float) -> float:
        idx = int(p / 100 * n)
        return sorted_lat[min(idx, n - 1)]

    p50 = percentile(50)
    p95 = percentile(95)
    mean = statistics.mean(latencies)
    min_lat = min(latencies)
    max_lat = max(latencies)

    print("\n── Latency Report ──────────────────────────────────")
    print(f"  Tickets submitted : {TOTAL_TICKETS}")
    print(f"  Tickets succeeded : {n}")
    print(f"  P50               : {p50:.3f}s")
    print(f"  P95               : {p95:.3f}s")
    print(f"  Mean              : {mean:.3f}s")
    print(f"  Min               : {min_lat:.3f}s")
    print(f"  Max               : {max_lat:.3f}s")
    print("────────────────────────────────────────────────────\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    """Run the full load test: preflight → register → submit → report."""
    print("── NeuraDesk Load Test ──────────────────────────────")
    print(f"  Backend         : {BASE_URL}")
    print(f"  Enterprise API  : {ENTERPRISE_URL}")

    preflight_enterprise_api()
    print("  Enterprise API  : OK")

    with httpx.Client() as client:
        token = register_test_user(client)

    latencies = asyncio.run(run_load_test(token))
    report(latencies)


if __name__ == "__main__":
    main()
