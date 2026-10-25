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
