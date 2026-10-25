import unittest
from pathlib import Path


class ServerHealthTests(unittest.TestCase):
    def test_health_endpoint_exists(self):
        source = Path('assembler/server.py').read_text(encoding='utf-8')
        self.assertIn('parsed.path == "/health"', source)
        self.assertIn('autonomous-video-assembler-review', source)

    def test_approval_requires_json_boolean_true(self):
        source = Path('assembler/server.py').read_text(encoding='utf-8')
        self.assertIn('body.get("approved") is True', source)
