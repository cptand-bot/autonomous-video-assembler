import unittest
from unittest.mock import patch

from assembler.media import MediaError


class VideoMediaTests(unittest.TestCase):
    @patch("assembler.media.urlopen")
    @patch("assembler.media.subprocess.run")
    def test_video_probe_rejects_zero_duration(self, run, open_url):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return b"video"
        open_url.return_value = Response()
        run.return_value.returncode = 0; run.return_value.stdout = '{"format":{"duration":"0"}}'; run.return_value.stderr = ''
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from assembler.media import download_video
        with TemporaryDirectory() as directory:
            with self.assertRaises(MediaError): download_video("https://example/video.mp4", Path(directory), "1")
