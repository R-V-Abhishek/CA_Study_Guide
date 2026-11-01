"""Graceful polling lifecycle for the PostgreSQL intelligence queue."""
import logging
import signal
import threading
import time
from pathlib import Path
from caf_common.heartbeat import write_heartbeat
from caf_common.logging import setup_logging
from caf_common.settings import get_settings
from caf_db.engine import get_session_factory
from caf_l5.jobs import run_worker_once

HEARTBEAT_INTERVAL_SECONDS = 30.0


def main(poll_seconds: float = 2.0) -> None:
    stopped = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    setup_logging()
    logging.basicConfig(level=logging.INFO)  # plain-text fallback for stdlib records outside production
    factory = get_session_factory("operations")
    logging.info("Intelligence worker started")
    beat_at = 0.0
    while not stopped.is_set():
        if time.monotonic() - beat_at >= HEARTBEAT_INTERVAL_SECONDS:
            beat_at = time.monotonic()
            try:
                write_heartbeat(Path(get_settings().storage.backup_dir))
            except OSError:
                logging.exception("Could not record the worker heartbeat; monitoring will report this worker as stale")
        try:
            job_id = run_worker_once(factory)
            if job_id is not None:
                logging.info("Completed intelligence job %s", job_id)
                continue
        except Exception:
            logging.exception("Intelligence job failed; failure recorded in queue")
        stopped.wait(poll_seconds)

    logging.info("Intelligence worker stopped")
