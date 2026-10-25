import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assembler.fetch_job import fetch_job


class FetchJobTests(unittest.TestCase):
    @patch("assembler.fetch_job.search_sources_detailed", return_value={"options": [{"src": "test"}], "errors": []})
    def test_writes_options_and_report(self, search):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scenes.json").write_text(json.dumps({"scenes": [{"id": 1, "source": "press_photo", "source_query": "самолёт"}]}), encoding="utf-8")
            report = fetch_job(root, 2)
            self.assertEqual(report["with_options"], 1)
            self.assertEqual(json.loads((root / "search_options.json").read_text(encoding="utf-8"))["1"][0]["src"], "test")
