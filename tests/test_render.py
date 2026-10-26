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
            # Рендер идёт только по утверждению человека, иначе смысла в
            # дашборде нет: раньше approval.json не читал никто.
            (root / "approval.json").write_text(json.dumps({"approved": True}), encoding="utf-8")
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
            (root / "approval.json").write_text(json.dumps({"approved": True}), encoding="utf-8")
            result = render_video(root, root / "out.mp4")
            self.assertEqual(result["status"], "rendered")
            first = run.call_args_list[0].args[0]
            self.assertIn("color=c=0x171522:s=1920x1080:r=25", first)

    def test_scene_filter_contains_overlay_text_and_ticker(self):
        result = scene_filter(Path('.'), {"id": 1}, {"text": {"words": "Проверка", "at": 1}, "ticker": {"words": "Ticker", "at": 2}})
        self.assertIn("drawtext", result)
        # Надписи идут КАПСОМ на тёмной пластине: жёлтый с обводкой запрещён.
        self.assertIn("TICKER", result)
        self.assertIn("box=1:boxcolor=0x14161a@0.82", result)
        self.assertIn("x=(w-text_w)/2:y=(h-text_h)/2", scene_filter(Path('.'), {"id": 1}, {"text": {"words": "Центр", "pos": "mc"}}))
        self.assertEqual(text_position("bad"), ("80", "80"))

    def test_scene_has_motion_and_no_black_bars(self):
        result = scene_filter(Path('.'), {"id": 1, "duration_sec": 11.0}, {})
        # Медленный зум в одну сторону вместо неподвижного фото на 11 секунд.
        self.assertIn("zoompan=z='1+0.045*on/275'", result)
        # Фон — размытая копия кадра, а не чёрные поля: 23 кадра из 55 были
        # не 16:9, у вертикальных экран был чёрным на две трети.
        self.assertIn("gblur=sigma=30", result)
        self.assertNotIn("pad=1920:1080", result)

    def test_video_scene_is_not_zoomed(self):
        result = scene_filter(Path('.'), {"id": 1, "duration_sec": 8.0}, {}, is_video=True)
        self.assertNotIn("zoompan", result)

    def test_photo_overlay_uses_second_input_filter_graph(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); photo = root / "overlay.png"; photo.write_bytes(b"x")
            result = scene_filter(root, {"id": 1, "duration_sec": 10.0}, {"photo": "overlay.png"})
            self.assertIn("[0:v]", result)
            self.assertIn("[1:v]", result)
            # Размер считается ОТ КАДРА (34% ширины 1920 = 652), а не от размера
            # исходного фото: иначе крупное фото накрывает пол-экрана, а мелкое
            # становится микроскопическим.
            self.assertIn("scale=652:-1", result)
            self.assertNotIn("scale=iw*", result)
            # Угол, никогда не центр: центр занят лицом или предметом.
            self.assertIn("overlay=W-w-70:70", result)
            # Всплывашка ДЕРЖИТ сцену, а не мелькает жёстко заданные 3 секунды.
            self.assertIn("between(t,3.5,9.7)", result)
            result = scene_filter(root, {"id": 1}, {"photo": "overlay.png", "text": {"words": "Текст"}, "ticker": {"words": "Лента"}})
            self.assertIn("ТЕКСТ", result)
            self.assertIn("ЛЕНТА", result)
            self.assertIn("[vout]", result)

    def test_ass_generation_has_valid_timestamps(self):
        text = scenes_to_ass([{"start_sec": 0, "duration_sec": 1.25, "text": "Тест {экрана}"}])
        self.assertIn("Dialogue: 0,0:00:00.00,0:00:01.25", text)
        self.assertNotIn("Тест {экрана}", text)
        self.assertEqual(ass_time(61.5), "0:01:01.50")

    def test_render_refuses_without_human_approval(self):
        """Утверждение человека — ЕДИНСТВЕННЫЙ вход в рендер.

        Было: approval.json не читал никто, кнопка «Утвердить ролик» была
        украшением, а джоб render в workflow рендерил артефакт того же прогона —
        то есть до того, как человек что-то увидел.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "images").mkdir(); (root / "images" / "001.jpg").write_bytes(b"x")
            (root / "scenes.json").write_text(json.dumps({"scenes": [{"id": 1, "duration_sec": 1}]}), encoding="utf-8")
            (root / "images" / "manifest.json").write_text(json.dumps({"1": {"path": "images/001.jpg"}}), encoding="utf-8")
            with self.assertRaises(RenderError) as caught:
                render_video(root, root / "out.mp4")
            self.assertIn("не утверждён человеком", str(caught.exception))
