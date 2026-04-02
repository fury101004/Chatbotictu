import shutil
import unittest
from io import BytesIO
from pathlib import Path
from unittest import mock

from fastapi import UploadFile

from app.data import clean_raw
from app.services import knowledge_base_service


class UploadMarkdownSupportTests(unittest.TestCase):
    def test_validated_uploads_accept_markdown_files(self):
        upload = UploadFile(filename="bhyt.md", file=BytesIO(b"# BHYT\n\nNoi dung"))
        validated = knowledge_base_service._validated_uploads([upload])

        self.assertEqual(len(validated), 1)
        self.assertEqual(validated[0].filename, "bhyt.md")
        upload.file.close()

    def test_validated_uploads_reject_unsupported_extensions(self):
        upload = UploadFile(filename="bhyt.txt", file=BytesIO(b"Noi dung"))

        with self.assertRaisesRegex(ValueError, "Markdown"):
            knowledge_base_service._validated_uploads([upload])

        upload.file.close()

    def test_build_clean_markdown_preserves_markdown_content(self):
        workspace_root = Path(__file__).resolve().parents[1]
        temp_root = workspace_root / "_test_clean_raw_workspace"
        shutil.rmtree(temp_root, ignore_errors=True)

        try:
            raw_root = temp_root / "datadoan"
            clean_root = temp_root / "clean_md"
            source_dir = raw_root / "_uploads" / "policy"
            source_dir.mkdir(parents=True, exist_ok=True)

            source_path = source_dir / "bhyt.md"
            source_path.write_text(
                "---\n"
                'title: "BHYT 2025"\n'
                "---\n\n"
                "Thong tin bao hiem y te.\n\n"
                "- Han nop: 30/09/2025\n"
                "- Doi tuong: sinh vien chinh quy\n",
                encoding="utf-8",
            )

            with mock.patch.object(clean_raw, "RAW_DATA_DIR", raw_root), mock.patch.object(
                clean_raw, "CLEAN_MD_DIR", clean_root
            ):
                stats = clean_raw.build_clean_markdown(route="policy", ocr_mode="auto")

            output_path = clean_root / "_uploads" / "policy" / "bhyt.md"
            self.assertTrue(output_path.exists())

            content = output_path.read_text(encoding="utf-8").replace("\\", "/")
            self.assertIn('title: "BHYT 2025"', content)
            self.assertIn('source_file: "_uploads/policy/bhyt.md"', content)
            self.assertIn('source_type: "md"', content)
            self.assertIn("# BHYT 2025", content)
            self.assertIn("- Han nop: 30/09/2025", content)
            self.assertEqual(stats["converted"], 1)
            self.assertEqual(stats["md_files"], 1)
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
