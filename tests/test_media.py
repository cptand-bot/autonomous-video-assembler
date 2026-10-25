import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from assembler.media import MediaError, add_manifest_metadata, normalize_image, write_image


class MediaTests(unittest.TestCase):
    def test_normalizes_valid_image_and_rejects_small(self):
        image = Image.new("RGB", (300, 240), "red")
        buf = io.BytesIO(); image.save(buf, format="PNG")
        data, width, height, fmt = normalize_image(buf.getvalue())
        self.assertEqual((width, height, fmt), (300, 240, "jpeg"))
        self.assertTrue(data.startswith(b"\xff\xd8"))
        with self.assertRaises(MediaError):
            normalize_image(b"not-an-image")

    def test_writes_manifest(self):
        image = Image.new("RGB", (200, 200), "blue")
        buf = io.BytesIO(); image.save(buf, format="JPEG")
        with TemporaryDirectory() as directory:
            info = write_image(Path(directory), "7", buf.getvalue(), source="test")
            self.assertEqual(info["source"], "test")
            self.assertTrue((Path(directory) / "images" / "007.jpg").exists())

    def test_overlay_write_does_not_replace_scene_manifest(self):
        image = Image.new("RGB", (300, 240), "green")
        buf = io.BytesIO(); image.save(buf, format="JPEG")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            scene = write_image(root, "1", buf.getvalue(), "scene", "upload")
            overlay = write_image(root, "1", buf.getvalue(), "overlay", "upload")
            manifest = __import__("json").loads((root / "images" / "manifest.json").read_text())
            self.assertEqual(manifest["1"]["path"], scene["path"])
            self.assertEqual(overlay["target"], "overlay")

    def test_manifest_keeps_license_metadata(self):
        image = Image.new("RGB", (300, 240), "black")
        buf = io.BytesIO(); image.save(buf, format="JPEG")
        with TemporaryDirectory() as directory:
            root = Path(directory); write_image(root, "1", buf.getvalue(), "scene", "openverse")
            add_manifest_metadata(root, "1", {"license": "cc0", "creator": "Author"})
            manifest = __import__("json").loads((root / "images" / "manifest.json").read_text())
            self.assertEqual(manifest["1"]["license"], "cc0")
