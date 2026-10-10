"""Background job runner: one thread, jobs run one at a time in order."""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from sqlalchemy import select

from .db import session_scope
from .models import Job

log = logging.getLogger("worker")


class Worker:
    def __init__(self, handler, poll_s: float = 1.0):
        self.handler, self.poll_s = handler, poll_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        with session_scope() as db:   # jobs cut off by a restart
            for j in db.scalars(select(Job).where(Job.status.in_(["running"]))):
                j.status, j.message = "failed", "Interrupted by a restart. Start grading again."
        self._thread = threading.Thread(target=self._loop, name="grading-worker", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(5)

    def run_once(self) -> bool:
        with session_scope() as db:
            j = db.scalar(select(Job).where(Job.status == "queued").order_by(Job.id).limit(1))
            if not j:
                return False
            j.status = "running"
            job_id = j.id
        try:
            res = self.handler(job_id)
            with session_scope() as db:
                j = db.get(Job, job_id)
                j.status, j.progress = "done", j.total
                j.message = (f"Graded {res['submissions']} submission(s); "
                             f"{res['similar_pairs']} similar pair(s) found.")
                j.finished_at = datetime.now(timezone.utc)
        except Exception as e:
            log.exception("job %s failed", job_id)
            with session_scope() as db:
                j = db.get(Job, job_id)
                j.status, j.message = "failed", f"{e}"[:2000]
                j.finished_at = datetime.now(timezone.utc)
        return True

    def _loop(self):
        while not self._stop.is_set():
            try:
                if not self.run_once():
                    self._stop.wait(self.poll_s)
            except Exception:
                log.exception("worker loop error")
                self._stop.wait(5)
