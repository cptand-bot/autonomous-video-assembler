import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assembler.render import RenderError, render_video
from assembler.render import scene_filter, text_position
from assembler.captions import ass_time, scenes_to_ass


class RenderTests(unittest.TestCase):
    def test_requires_manifest_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scenes.json").write_text(json.dumps({"scenes": [{"id": 1, "duration_sec": 1}]}), encoding="utf-8")
            with self.assertRaises(RenderError):
                render_video(root, root / "out.mp4")

    def test_rejects_failed_manifest_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "images").mkdir(); (root / "images" / "001.jpg").write_bytes(b"x")
            (root / "scenes.json").write_text(json.dumps({"scenes": [{"id": 1, "duration_sec": 1, "source": "press_photo"}]}), encoding="utf-8")
            (root / "images" / "manifest.json").write_text(json.dumps({"1": {"path": "images/001.jpg", "status": "FAILED"}}), encoding="utf-8")
            with self.assertRaises(RenderError):
                render_video(root, root / "out.mp4")

    @patch("assembler.render.subprocess.run")
    def test_render_invokes_ffmpeg_for_each_scene(self, run):
        run.return_value.returncode = 0
        run.return_value.stderr = b""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "images").mkdir(); (root / "images" / "001.jpg").write_bytes(b"x")
            (root / "scenes.json").write_text(json.dumps({"scenes": [{"id": 1, "duration_sec": 1}]}), encoding="utf-8")
            (root / "images" / "manifest.json").write_text(json.dumps({"1": {"path": "images/001.jpg"}}), encoding="utf-8")
            result = render_video(root, root / "out.mp4")
            self.assertEqual(result["status"], "rendered")
            self.assertGreaterEqual(run.call_count, 2)

    @patch("assembler.render.subprocess.run")
    def test_card_scene_renders_without_media_manifest(self, run):
        run.return_value.returncode = 0
        run.return_value.stderr = b""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scenes.json").write_text(json.dumps({"scenes": [{"id": 1, "duration_sec": 1, "source": "card:quote", "text": "Карточка"}]}), encoding="utf-8")
            result = render_video(root, root / "out.mp4")
            self.assertEqual(result["status"], "rendered")
            first = run.call_args_list[0].args[0]
            self.assertIn("color=c=0x171522:s=1920x1080:r=25", first)

    def test_scene_filter_contains_overlay_text_and_ticker(self):
        result = scene_filter(Path('.'), {"id": 1}, {"text": {"words": "Проверка", "at": 1}, "ticker": {"words": "Ticker", "at": 2}})
        self.assertIn("drawtext", result)
        self.assertIn("Ticker", result)
        self.assertIn("x=(w-text_w)/2:y=(h-text_h)/2", scene_filter(Path('.'), {"id": 1}, {"text": {"words": "Центр", "pos": "mc"}}))
        self.assertEqual(text_position("bad"), ("80", "80"))

    def test_photo_overlay_uses_second_input_filter_graph(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); photo = root / "overlay.png"; photo.write_bytes(b"x")
            result = scene_filter(root, {"id": 1}, {"photo": "overlay.png", "pos": {"x": 20, "y": 30}})
            self.assertIn("[0:v]", result)
            self.assertIn("[1:v]", result)
            self.assertIn("overlay=20:30", result)
            self.assertIn("scale=iw*1.0:ih*1.0", result)
            result = scene_filter(root, {"id": 1}, {"photo": "overlay.png", "text": {"words": "Текст"}, "ticker": {"words": "Лента"}})
            self.assertIn("Текст", result)
            self.assertIn("Лента", result)
            self.assertIn("[vout]", result)

    def test_ass_generation_has_valid_timestamps(self):
        text = scenes_to_ass([{"start_sec": 0, "duration_sec": 1.25, "text": "Тест {экрана}"}])
        self.assertIn("Dialogue: 0,0:00:00.00,0:00:01.25", text)
        self.assertNotIn("Тест {экрана}", text)
        self.assertEqual(ass_time(61.5), "0:01:01.50")
