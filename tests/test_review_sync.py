import unittest
import json
import tempfile
from pathlib import Path

from assembler.storage import JobStore


class ReviewSyncTests(unittest.TestCase):
    def test_review_uses_live_thumb_state(self):
        source = Path('assembler/dashboard.py').read_text(encoding='utf-8')
        # Путь к кадру ОТНОСИТЕЛЬНЫЙ: он обязан работать и с сервера, и когда
        # человек открыл скачанный артефакт файлом с диска. Ведущая косая черта
        # делает путь абсолютным, и с диска картинка не грузится.
        self.assertIn("if(s.thumb)state[s.id].image=s.thumb", source)
        self.assertNotIn("state[s.id].image='/'+s.thumb", source)
        self.assertIn("/state?_probe=1", source)

    def test_review_embeds_relative_media_and_overlays(self):
        from assembler.dashboard import render_review
        page = render_review({
            "channel": "ПЛАНЕТА",
            "scenes": [{"id": 1, "text": "т", "start_sec": 0.0, "duration_sec": 5.0,
                        "source": "press_photo", "source_query": "з"}],
            "assets": {"1": {"image": "images/001.jpg", "status": "ok"}},
            "overlays": {"1": {"planned": True, "photo": "overlays/scene_001.jpg"}},
        })
        self.assertIn("images/001.jpg", page)
        self.assertIn("overlays/scene_001.jpg", page)
        self.assertNotIn('src="/', page)

    def test_frame_change_invalidates_previous_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = JobStore(root)
            (root / "approval.json").write_text(json.dumps({"approved": True}), encoding="utf-8")
            store.mark_need("7")
            state = json.loads((root / "approval.json").read_text(encoding="utf-8"))
            self.assertFalse(state["approved"])

    def test_placeholder_manifest_is_failed_in_review_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "images").mkdir()
            (root / "scenes.json").write_text(json.dumps({"scenes": [{"id": 1}]}), encoding="utf-8")
            (root / "images" / "001.jpg").write_bytes(b"x")
            (root / "images" / "manifest.json").write_text(json.dumps({"1": {"path": "images/001.jpg", "status": "placeholder"}}), encoding="utf-8")
            scene = JobStore(root).state()["scenes"][0]
            self.assertEqual(scene["status"], "failed")
            self.assertEqual(scene["media_status"], "placeholder")

    def test_state_exposes_media_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "images").mkdir()
            (root / "scenes.json").write_text(json.dumps({"scenes": [{"id": 1}]}), encoding="utf-8")
            (root / "images" / "001.jpg").write_bytes(b"x")
            (root / "images" / "manifest.json").write_text(json.dumps({"1": {"path": "images/001.jpg", "status": "ok", "url": "https://example.test/x", "license": "cc0", "creator": "A"}}), encoding="utf-8")
            scene = JobStore(root).state()["scenes"][0]
            self.assertEqual((scene["url"], scene["license"], scene["creator"]), ("https://example.test/x", "cc0", "A"))
