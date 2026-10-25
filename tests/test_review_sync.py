import unittest
from pathlib import Path


class ReviewSyncTests(unittest.TestCase):
    def test_review_uses_live_thumb_state(self):
        source = Path('assembler/dashboard.py').read_text(encoding='utf-8')
        self.assertIn("if(s.thumb)state[s.id].image='/'+s.thumb", source)
        self.assertIn("/state?_probe=1", source)
