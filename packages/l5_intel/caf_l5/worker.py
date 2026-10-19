"""Graceful polling lifecycle for the PostgreSQL intelligence queue."""
import logging
import signal
import threading
from caf_db.engine import get_session_factory
from caf_l5.jobs import run_worker_once


def main(poll_seconds: float = 2.0) -> None:
    stopped = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    logging.basicConfig(level=logging.INFO)
    factory = get_session_factory("operations")
    logging.info("Intelligence worker started")
    while not stopped.is_set():
        try:
            job_id = run_worker_once(factory)
            if job_id is not None:
                logging.info("Completed intelligence job %s", job_id)
                continue
        except Exception:
            logging.exception("Intelligence job failed; failure recorded in queue")
        stopped.wait(poll_seconds)

    logging.info("Intelligence worker stopped")
