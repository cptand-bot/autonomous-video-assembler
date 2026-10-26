import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from assembler.overlays import plan_overlays

from assembler.pipeline import run_pipeline


class PipelineTests(unittest.TestCase):
    def test_plans_text_overlays_with_spacing_and_complete_fields(self):
        scenes = [{"id": i, "duration_sec": 11.5, "source": "press_photo", "text": "Это законченная фраза о событии и его последствиях для города и людей."} for i in range(1, 40)]
        overlays = plan_overlays(scenes)
        ids = [int(k) for k in overlays if k != "anchor"]
        self.assertEqual(len(ids), 3)
        self.assertGreaterEqual(ids[1] - ids[0], 9)
        self.assertNotEqual(overlays[str(ids[0])]["style"], overlays[str(ids[1])]["style"])
        for sid in ids:
            item = overlays[str(sid)]
            self.assertTrue(item["text"]["words"])
            for key in ("at", "shape", "style", "size", "scale", "sound", "anchor"):
                self.assertIn(key, item)
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

    @patch("assembler.pipeline.fetch_job", return_value={"scenes": 1, "with_options": 0, "errors": []})
    def test_approval_blocks_failed_manifest(self, fetch):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "images").mkdir()
            (root / "scenes.json").write_text(json.dumps({"scenes": [{"id": 1, "source": "press_photo"}]}), encoding="utf-8")
            (root / "images" / "manifest.json").write_text(json.dumps({"1": {"path": "images/001.jpg", "status": "FAILED"}}), encoding="utf-8")
            result = run_pipeline(root, root / "out.mp4", approve=True)
            self.assertEqual(result["status"], "blocked")

    def test_pipeline_cli_has_nonzero_blocked_exit(self):
        source = Path("assembler/pipeline.py").read_text(encoding="utf-8")
        self.assertIn("raise SystemExit(2)", source)
