import unittest
from pathlib import Path


class ServerMediaTests(unittest.TestCase):
    def test_server_has_video_route(self):
        source = Path('assembler/server.py').read_text(encoding='utf-8')
        self.assertIn('parsed.path.startswith("/videos/")', source)
        self.assertIn('video/mp4', source)
        self.assertIn('Content-Range', source)
        self.assertIn('Accept-Ranges', source)
