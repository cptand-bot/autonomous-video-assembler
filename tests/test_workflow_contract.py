import unittest
from pathlib import Path


class WorkflowContractTests(unittest.TestCase):
    def test_workflow_contains_review_gate_and_final_artifact(self):
        workflow = Path('.github/workflows/test-srt-dashboard.yml').read_text(encoding='utf-8')
        self.assertIn('inputs.approve == true', workflow)
        self.assertIn('name: final-video', workflow)
        self.assertIn('build/output.mp4', workflow)
        self.assertIn('fetch-review:', workflow)
        self.assertIn('needs: fetch-review', workflow)
        self.assertIn('actions/download-artifact@v4', workflow)
        self.assertIn('sudo apt-get install -y ffmpeg', workflow)
        self.assertIn('permissions:', workflow)
        self.assertGreaterEqual(workflow.count('retention-days: 1'), 3)
        self.assertIn('Check optional API configuration', workflow)
        self.assertNotIn('echo "$PEXELS_API_KEY"', workflow)
