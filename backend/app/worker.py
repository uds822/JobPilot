"""Standalone background worker service for JobPilot.

Continuously runs Company Watch ATS discovery, job ingestion,
and description enrichment at configured intervals.
"""

import asyncio
import logging
import os
import signal
import sys

from app.company_watch.discovery import discover_due_companies
from app.company_watch.service import ingest_due_sources
from app.core.logging import setup_logging

setup_logging()
logger = logging.getLogger("jobpilot.worker")

POLL_INTERVAL_SECONDS = int(os.getenv("WORKER_INTERVAL_SECONDS", "300"))
DISCOVERY_LIMIT = int(os.getenv("WORKER_DISCOVERY_LIMIT", "20"))
INGESTION_LIMIT = int(os.getenv("WORKER_INGESTION_LIMIT", "20"))
CONCURRENCY = int(os.getenv("WORKER_CONCURRENCY", "4"))

_stop_event = asyncio.Event()


def _handle_shutdown_signal(sig_name: str):
    logger.info("Received %s, signaling background worker to stop gracefully...", sig_name)
    _stop_event.set()


async def run_worker_loop():
    logger.info("JobPilot Background Worker started (poll interval: %ds)", POLL_INTERVAL_SECONDS)

    while not _stop_event.is_set():
        try:
            logger.info("--- Starting scheduled Company Watch cycle ---")

            # 1. Discover due companies
            logger.info("Running company discovery (limit=%d, concurrency=%d)...", DISCOVERY_LIMIT, CONCURRENCY)
            discovery_result = await discover_due_companies(
                limit=DISCOVERY_LIMIT,
                concurrency=CONCURRENCY,
            )
            logger.info("Discovery cycle completed: %s", discovery_result)

            if _stop_event.is_set():
                break

            # 2. Ingest due ATS sources
            logger.info("Running source ingestion (limit=%d, concurrency=%d)...", INGESTION_LIMIT, CONCURRENCY)
            ingest_result = await ingest_due_sources(
                limit=INGESTION_LIMIT,
                concurrency=CONCURRENCY,
            )
            logger.info(
                "Ingestion cycle completed: claimed=%s, raw_jobs=%s, india_jobs=%s, inserted=%s, updated=%s",
                ingest_result.get("claimed", 0),
                ingest_result.get("raw_jobs", 0),
                ingest_result.get("india_jobs", 0),
                ingest_result.get("inserted", 0),
                ingest_result.get("updated", 0),
            )

        except Exception as exc:
            logger.exception("Unexpected error in worker loop: %s", exc)

        logger.info("Sleeping for %d seconds until next cycle...", POLL_INTERVAL_SECONDS)
        try:
            await asyncio.wait_for(_stop_event.wait(), timeout=POLL_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass

    logger.info("JobPilot Background Worker shut down cleanly.")


def main():
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Register OS signal handlers for graceful shutdown on POSIX systems
    if sys.platform != "win32":
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, _handle_shutdown_signal, sig.name)

    try:
        loop.run_until_complete(run_worker_loop())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker interrupted by user.")
    finally:
        loop.close()


if __name__ == "__main__":
    main()

