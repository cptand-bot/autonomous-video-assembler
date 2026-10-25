import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assembler.pipeline import run_pipeline


class PipelineTests(unittest.TestCase):
    @patch("assembler.pipeline.fetch_job", return_value={"scenes": 1, "with_options": 0, "errors": []})
    def test_stops_at_review_gate(self, fetch):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "scenes.json").write_text(json.dumps({"scenes": []}), encoding="utf-8")
            result = run_pipeline(root, root / "out.mp4", approve=False)
            self.assertEqual(result["status"], "review_required")
            self.assertFalse((root / "out.mp4").exists())

    @patch("assembler.pipeline.fetch_job", return_value={"scenes": 1, "with_options": 1, "errors": []})
    @patch("assembler.pipeline.render_video", return_value={"status": "rendered", "scene_count": 1})
    def test_renders_only_after_approval(self, render, fetch):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "scenes.json").write_text(json.dumps({"scenes": []}), encoding="utf-8")
            result = run_pipeline(root, root / "out.mp4", approve=True)
            self.assertEqual(result["status"], "rendered")
            render.assert_called_once()
