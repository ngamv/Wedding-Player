from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from core.ceo_jobs import CEOJobs


class CEOJobsTests(TestCase):
    def test_deduplication_and_retry_preserve_attempts(self):
        with TemporaryDirectory() as tmp:
            queue = CEOJobs(Path(tmp) / "orion.db")
            today = date(2026, 11, 24)
            with ThreadPoolExecutor(max_workers=4) as pool:
                jobs = list(pool.map(lambda _: queue.enqueue(today, "dashboard"), range(4)))
            self.assertEqual(len({job["id"] for job in jobs}), 1)

            first = jobs[0]["id"]
            attempted = []
            def generate(day):
                attempted.append(day)
                return {"sources": {"Site web": "error"}, "file_sync": {}}

            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(lambda _: queue.run(first, generate), range(4)))
            self.assertEqual(attempted, [today])
            self.assertEqual(queue.list()[0]["state"], "failed")
            second = queue.enqueue(today, "dashboard")
            self.assertNotEqual(first, second["id"])
            queue.run(second["id"], lambda _: {"sources": {"Site web": "ok"}, "file_sync": {}})
            self.assertEqual([job["state"] for job in queue.list()], ["completed", "failed"])
