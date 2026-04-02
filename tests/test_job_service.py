import time
import unittest

from app.services.job_service import get_job, start_background_job


class JobServiceTests(unittest.TestCase):
    def test_background_job_completes_and_persists_result(self):
        def target(_job_id, progress):
            progress(progress=55, stage="vector_build", detail="Dang build vector store.")
            return {"message": "ok", "sync": {"route": "all"}}

        job = start_background_job(
            "knowledge_rebuild",
            target,
            payload={"route": "all"},
        )

        current = None
        for _ in range(100):
            current = get_job(job["id"])
            if current and current["status"] == "completed":
                break
            time.sleep(0.02)

        self.assertIsNotNone(current)
        self.assertEqual(current["status"], "completed")
        self.assertEqual(current["payload"]["route"], "all")
        self.assertEqual(current["result"]["message"], "ok")
        self.assertEqual(current["result"]["sync"]["route"], "all")


if __name__ == "__main__":
    unittest.main()
