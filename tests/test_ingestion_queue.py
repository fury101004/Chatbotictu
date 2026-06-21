from __future__ import annotations

import inspect
import shutil
import tempfile
import unittest
from pathlib import Path

from services.ingestion_queue import IngestionQueue


class FakeUpload:
    def __init__(self, filename: str, content: bytes) -> None:
        self.filename = filename
        self._content = content

    async def read(self) -> bytes:
        return self._content


class FakeBackgroundTasks:
    def __init__(self) -> None:
        self.tasks = []

    def add_task(self, func, *args, **kwargs) -> None:
        self.tasks.append((func, args, kwargs))

    async def run(self) -> None:
        for func, args, kwargs in self.tasks:
            result = func(*args, **kwargs)
            if inspect.isawaitable(result):
                await result


class IngestionQueueTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "ingestion.db"
        self.checkpoint_root = Path(self.temp_dir.name) / "ingestion_checkpoints"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def build_queue(self) -> IngestionQueue:
        return IngestionQueue(
            db_path=str(self.db_path),
            checkpoint_root=self.checkpoint_root,
        )

    async def test_job_creation_and_completion_status(self) -> None:
        queue = self.build_queue()
        background_tasks = FakeBackgroundTasks()

        async def processor(**kwargs):
            kwargs["progress_callback"]("extracting", 25)
            kwargs["progress_callback"]("chunking", 45)
            kwargs["progress_callback"]("embedding", 65)
            kwargs["progress_callback"]("indexing", 85)
            return {"status": "success", "indexed": len(kwargs["files"])}

        queued = await queue.enqueue_upload(
            files=[FakeUpload("guide.md", b"# Guide")],
            tool_name="student_faq_rag",
            processor=processor,
            background_tasks=background_tasks,
        )

        self.assertEqual(queued["status"], "queued")
        self.assertEqual(queued["progress"], 0)

        await background_tasks.run()
        completed = queue.get_status(queued["job_id"])

        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["progress"], 100)
        self.assertEqual(completed["result"]["indexed"], 1)
        self.assertNotIn("checkpoint_path", completed)
        self.assertFalse((self.checkpoint_root / queued["job_id"]).exists())

    async def test_failed_job_records_error(self) -> None:
        queue = self.build_queue()
        background_tasks = FakeBackgroundTasks()

        async def processor(**kwargs):
            raise RuntimeError("index failed")

        queued = await queue.enqueue_upload(
            files=[FakeUpload("guide.md", b"# Guide")],
            tool_name="student_faq_rag",
            processor=processor,
            background_tasks=background_tasks,
        )

        await background_tasks.run()
        failed = queue.get_status(queued["job_id"])

        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["progress"], 100)
        self.assertIn("index failed", failed["error"])

    async def test_status_polling_returns_not_found_for_unknown_job(self) -> None:
        status = self.build_queue().get_status("missing")

        self.assertEqual(status["status"], "not_found")

    async def test_unfinished_job_resumes_after_restart_from_durable_checkpoint(self) -> None:
        background_tasks = FakeBackgroundTasks()
        queue = self.build_queue()

        queued = await queue.enqueue_upload(
            files=[FakeUpload("guide.md", b"# Guide")],
            tool_name="student_faq_rag",
            processor=lambda **kwargs: None,
            background_tasks=background_tasks,
        )

        restarted_queue = self.build_queue()
        processed_files: list[tuple[str, bytes]] = []

        async def processor(**kwargs):
            for file in kwargs["files"]:
                processed_files.append((file.filename, await file.read()))
            kwargs["progress_callback"]("indexing", 85)
            return {"status": "success", "indexed": len(processed_files)}

        resumed = await restarted_queue.resume_pending_uploads(processor=processor)
        await restarted_queue.wait_for_active_jobs()
        completed = restarted_queue.get_status(queued["job_id"])

        self.assertEqual(resumed, 1)
        self.assertEqual(processed_files, [("guide.md", b"# Guide")])
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["resume_count"], 1)
        self.assertFalse((self.checkpoint_root / queued["job_id"]).exists())

    async def test_missing_checkpoint_is_marked_interrupted_after_restart(self) -> None:
        background_tasks = FakeBackgroundTasks()
        queue = self.build_queue()
        queued = await queue.enqueue_upload(
            files=[FakeUpload("guide.md", b"# Guide")],
            tool_name="student_faq_rag",
            processor=lambda **kwargs: None,
            background_tasks=background_tasks,
        )
        shutil.rmtree(self.checkpoint_root / queued["job_id"])

        restarted_queue = self.build_queue()
        resumed = await restarted_queue.resume_pending_uploads(
            processor=lambda **kwargs: None,
        )
        interrupted = restarted_queue.get_status(queued["job_id"])

        self.assertEqual(resumed, 0)
        self.assertEqual(interrupted["status"], "interrupted")
        self.assertIn("checkpoint", interrupted["error"])


if __name__ == "__main__":
    unittest.main()
