import unittest
import json
import tempfile
from pathlib import Path

from assembler.storage import JobStore


class ReviewSyncTests(unittest.TestCase):
    def test_review_uses_live_thumb_state(self):
        source = Path('assembler/dashboard.py').read_text(encoding='utf-8')
        self.assertIn("if(s.thumb)state[s.id].image='/'+s.thumb", source)
        self.assertIn("/state?_probe=1", source)

    def test_frame_change_invalidates_previous_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = JobStore(root)
            (root / "approval.json").write_text(json.dumps({"approved": True}), encoding="utf-8")
            store.mark_need("7")
            state = json.loads((root / "approval.json").read_text(encoding="utf-8"))
            self.assertFalse(state["approved"])

    def test_placeholder_manifest_is_failed_in_review_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "images").mkdir()
            (root / "scenes.json").write_text(json.dumps({"scenes": [{"id": 1}]}), encoding="utf-8")
            (root / "images" / "001.jpg").write_bytes(b"x")
            (root / "images" / "manifest.json").write_text(json.dumps({"1": {"path": "images/001.jpg", "status": "placeholder"}}), encoding="utf-8")
            self.assertEqual(JobStore(root).state()["scenes"][0]["status"], "failed")
