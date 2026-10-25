import json
import tempfile
import unittest
from pathlib import Path

from assembler.selfcheck import check_job


class SelfcheckTests(unittest.TestCase):
    def test_detects_missing_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "scenes.json").write_text(json.dumps({"scenes": [{"id": 1}]}), encoding="utf-8")
            self.assertTrue(any("missing manifest" in x for x in check_job(root)))

    def test_accepts_existing_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "images").mkdir(); (root / "images/001.jpg").write_bytes(b"x")
            (root / "scenes.json").write_text(json.dumps({"scenes": [{"id": 1}]}), encoding="utf-8")
            (root / "images/manifest.json").write_text(json.dumps({"1": {"path": "images/001.jpg"}}), encoding="utf-8")
            self.assertEqual(check_job(root), [])

    def test_card_scene_does_not_require_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "scenes.json").write_text(json.dumps({"scenes": [{"id": 1, "source": "card:quote"}]}), encoding="utf-8")
            self.assertEqual(check_job(root), [])
