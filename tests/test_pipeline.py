import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from assembler.overlays import plan_overlays
from assembler.storyboard import build_search_query

from assembler.pipeline import run_pipeline


class PipelineTests(unittest.TestCase):
    def test_query_builder_does_not_use_narration_prefix_or_topic_suffix(self):
        narration = "правильные произносит их человек который находится в этой истории"
        query = build_search_query(narration, set(), "Илон Маск Starlink Украина")
        self.assertNotEqual(query.split()[:2], narration.split()[:2])
        self.assertNotIn("реальное фото", query)
        self.assertNotIn("Starlink Украина", query)

    def test_plans_text_overlays_with_spacing_and_complete_fields(self):
        # Сцена без НАЗВАННОГО предмета и без числа всплывашки не получает:
        # иначе в надпись уезжает пересказ озвучки, а это не иллюстрация.
        empty = [{"id": i, "duration_sec": 11.5, "source": "press_photo", "source_query": "объект события", "text": "Это законченная фраза о событии и его последствиях для города и людей."} for i in range(1, 40)]
        _, empty_stats = plan_overlays(empty, channel="5 МИНУТ")
        self.assertEqual(empty_stats["accepted"], 0)
        self.assertEqual(empty_stats["rejected_by_subtype"]["no_answer_to_what_it_illustrates"], 39)
        # А сцена с числом и с предметом, которого нет в базе, — получает.
        scenes = [{"id": i, "duration_sec": 11.5, "source": "press_photo", "source_query": "объект события",
                   "text": "За три дня компания Starlink отключила терминалы на участке фронта и связь пропала."} for i in range(1, 40)]
        overlays, stats = plan_overlays(scenes, channel="5 МИНУТ")
        ids = [int(k) for k in overlays if k != "anchor"]
        self.assertGreaterEqual(len(ids), 1)
        # Разрежение имеет СВОЮ причину, не смешанную со смысловым слоем.
        self.assertIn("too_close_to_previous", stats["rejected_by_subtype"])
        self.assertEqual(stats["proposed"], 39)
        self.assertEqual(stats["accepted"], len(ids))
        self.assertGreaterEqual(ids[1] - ids[0], 9)
        self.assertNotEqual(overlays[str(ids[0])]["style"], overlays[str(ids[1])]["style"])
        for sid in ids:
            item = overlays[str(sid)]
            self.assertTrue(item["text"]["words"])
            for key in ("at", "shape", "style", "size", "scale", "sound", "anchor"):
                self.assertIn(key, item)

    def test_planeta_never_gets_text_overlay(self):
        scenes = [{"id": 1, "duration_sec": 11.5, "source": "press_photo", "source_query": "здание ведомства", "text": "Двадцать второго октября власти расширили обязательную эвакуацию семей с детьми."}]
        overlays, _ = plan_overlays(scenes, channel="ПЛАНЕТА")
        self.assertEqual(overlays["1"]["text"]["disabled"], True)
    @patch("assembler.pipeline.fetch_job", return_value={"scenes": 1, "with_options": 0, "errors": []})
    def test_stops_at_review_gate(self, fetch):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "scenes.json").write_text(json.dumps({"scenes": []}), encoding="utf-8")
            result = run_pipeline(root, root / "out.mp4", approve=False)
            self.assertEqual(result["status"], "review_required")
            self.assertFalse((root / "out.mp4").exists())

    @patch("assembler.pipeline.fetch_job", return_value={"scenes": 1, "with_options": 1, "errors": []})
    @patch("assembler.pipeline.render_video", return_value={"status": "rendered", "scene_count": 1})
    def test_renders_only_after_approval(self, render, fetch):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "scenes.json").write_text(json.dumps({"scenes": []}), encoding="utf-8")
            result = run_pipeline(root, root / "out.mp4", approve=True)
            self.assertEqual(result["status"], "rendered")
            render.assert_called_once()

    @patch("assembler.pipeline.fetch_job", return_value={"scenes": 1, "with_options": 0, "errors": []})
    def test_approval_blocks_failed_manifest(self, fetch):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "images").mkdir()
            (root / "scenes.json").write_text(json.dumps({"scenes": [{"id": 1, "source": "press_photo"}]}), encoding="utf-8")
            (root / "images" / "manifest.json").write_text(json.dumps({"1": {"path": "images/001.jpg", "status": "FAILED"}}), encoding="utf-8")
            result = run_pipeline(root, root / "out.mp4", approve=True)
            self.assertEqual(result["status"], "blocked")

    def test_pipeline_cli_has_nonzero_blocked_exit(self):
        source = Path("assembler/pipeline.py").read_text(encoding="utf-8")
        self.assertIn("raise SystemExit(2)", source)
