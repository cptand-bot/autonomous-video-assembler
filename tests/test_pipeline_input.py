import unittest
from pathlib import Path


class PipelineInputTests(unittest.TestCase):
    def test_workflow_exposes_srt_and_audio_inputs(self):
        text = Path('.github/workflows/test-srt-dashboard.yml').read_text(encoding='utf-8')
        self.assertIn('srt_path:', text)
        self.assertIn('audio_path:', text)
        self.assertIn('--audio', text)
