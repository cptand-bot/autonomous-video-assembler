"""Решения человека с дашборда ДОЕЗЖАЮТ до сборки.

Было: кнопки дашборда писали в сторону локального сервера, которого в облаке
нет; `render.py` не читал `approval.json` вообще; джоб `render` рендерил
артефакт того же прогона, то есть до просмотра. Решения умирали на диске.
"""

import base64
import io
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from assembler.apply_changes import apply_changes


def data_url(width: int = 64, height: int = 36) -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "green").save(buffer, format="JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


class ApplyChangesTests(unittest.TestCase):
    def build(self, root: Path) -> None:
        (root / "images").mkdir(parents=True, exist_ok=True)
        for sid in ("1", "2", "3"):
            (root / "images" / f"{int(sid):03d}.jpg").write_bytes(b"frame")
        (root / "images" / "manifest.json").write_text(json.dumps({
            sid: {"path": f"images/{int(sid):03d}.jpg", "md5": "x", "status": "ok"} for sid in ("1", "2", "3")
        }), encoding="utf-8")
        (root / "overlays.json").write_text(json.dumps({"2": {"planned": True, "photo": "overlays/scene_002.jpg"}}), encoding="utf-8")

    def test_uploaded_photo_replaces_the_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.build(root)
            report = apply_changes(root, {"approved": True, "scenes": {"1": {"verdict": "replace", "upload": data_url()}}})
            self.assertEqual(report["replaced"], ["1"])
            manifest = json.loads((root / "images" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["1"]["source"], "upload")
            with Image.open(root / "images" / "001.jpg") as image:
                self.assertEqual(image.size, (64, 36))

    def test_banned_frame_is_removed_and_blocks_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.build(root)
            report = apply_changes(root, {"approved": True, "scenes": {"3": {"verdict": "ban", "note": "размыто"}}})
            self.assertEqual(report["banned"], ["3"])
            self.assertFalse((root / "images" / "003.jpg").exists())
            manifest = json.loads((root / "images" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["3"]["status"], "FAILED")
            # Утверждение снимается само: рендерить ролик с пустой сценой нельзя.
            self.assertFalse(report["approved"])
            approval = json.loads((root / "approval.json").read_text(encoding="utf-8"))
            self.assertFalse(approval["approved"])

    def test_overlay_edits_and_clearing_reach_overlays_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.build(root)
            apply_changes(root, {"approved": False, "scenes": {
                "1": {"overlay": {"text": {"words": "ТРИ ДНЯ"}, "at": 0.4, "scale": 1.2}},
                "2": {"overlay": {"cleared": True}},
            }})
            overlays = json.loads((root / "overlays.json").read_text(encoding="utf-8"))
            self.assertEqual(overlays["1"]["text"]["words"], "ТРИ ДНЯ")
            self.assertTrue(overlays["1"]["approved_by_human"])
            self.assertNotIn("2", overlays)

    def test_approval_passes_when_every_scene_has_a_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.build(root)
            report = apply_changes(root, {"approved": True, "scenes": {"1": {"verdict": "keep"}}})
            self.assertTrue(report["approved"])
            self.assertTrue(json.loads((root / "approval.json").read_text(encoding="utf-8"))["approved"])

    def test_broken_upload_is_reported_not_swallowed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.build(root)
            report = apply_changes(root, {"scenes": {"1": {"upload": "совсем не картинка"}}})
            self.assertTrue(report["errors"])
            self.assertIn("data URL", report["errors"][0])


if __name__ == "__main__":
    unittest.main()
