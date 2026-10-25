import json
import tempfile
import time
import unittest
from pathlib import Path

from PIL import Image

from assembler import guards
from assembler.validate import storyboard_review


def scene(sid: int, query: str, source: str = "press_photo", duration: float = 11.5) -> dict:
    return {
        "id": sid,
        "text": f"scene {sid}",
        "start_sec": round((sid - 1) * duration, 3),
        "duration_sec": duration,
        "visual_prompt": query,
        "source": source,
        "source_query": query,
    }


class HostFilterTests(unittest.TestCase):
    def test_banned_hosts_are_dropped(self):
        options = [
            {"full": "https://www.alamy.com/photo-123.jpg"},
            {"full": "https://avatars.mds.yandex.net/get-shedevrum/1/x.jpg"},
            {"full": "https://upload.wikimedia.org/real.jpg"},
        ]
        kept = guards.filter_candidates(options)
        self.assertEqual([o["full"] for o in kept], ["https://upload.wikimedia.org/real.jpg"])


class BanListTests(unittest.TestCase):
    def test_timed_ban_expires_but_permanent_stays(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "banned_md5.json"
            path.write_text(json.dumps({
                "aaa": {"reason": "watermark"},
                "bbb": {"reason": "seen too often", "until": time.time() - 10},
            }), encoding="utf-8")
            active = guards.load_bans(path)
            self.assertIn("aaa", active)
            self.assertNotIn("bbb", active)

    def test_banned_frame_in_build_is_found(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "images").mkdir()
            frame = root / "images" / "scene_001.jpg"
            Image.new("RGB", (1920, 1080), "navy").save(frame, "JPEG")
            hits = guards.banned_files(root, {guards.md5_of(frame): {"reason": "banned earlier"}})
            self.assertEqual(len(hits), 1)
            self.assertTrue(hits[0][0].endswith("scene_001.jpg"))


class QualityTests(unittest.TestCase):
    def test_narrow_frame_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            narrow = Path(directory) / "scene_002.jpg"
            Image.new("RGB", (1200, 800), "white").save(narrow, "JPEG")
            warnings = guards.quality_warnings([narrow])
            self.assertTrue(warnings)
            self.assertIn("width 1200", warnings[0])


class QueryLintTests(unittest.TestCase):
    def test_mine_in_russian_query(self):
        self.assertTrue(guards.lint_query("повестка вручение мобилизация", "press_photo"))

    def test_transport_stock_needs_a_closeup(self):
        self.assertTrue(guards.lint_query("traffic jam cars gridlock city street", "pexels_video"))
        self.assertFalse(guards.lint_query("brake lights red glow closeup", "pexels_video"))

    def test_press_must_be_russian(self):
        problems = guards.lint_query("ministry building facade", "press_photo")
        self.assertTrue(any("Russian" in problem for problem in problems))
        self.assertFalse(guards.lint_query("здание Министерства обороны России, реальное фото 2026", "press_photo"))

    def test_card_text_is_not_linted(self):
        self.assertEqual(guards.lint_query("Поджечь забор можно быстро", "card:quote"), [])

    def test_cross_check_catches_a_duplicate_between_layers(self):
        problems = guards.cross_check_queries([
            ("scene 53", "зал заседаний Евросовета Брюссель реальное фото"),
            ("overlay 16", "зал заседаний Евросовета Брюссель реальное фото"),
        ])
        self.assertTrue(problems)
        self.assertIn("duplicate query", problems[0])


class StoryboardNormTests(unittest.TestCase):
    def test_repeated_object_is_caught_while_strings_stay_unique(self):
        scenes = [
            scene(1, "трибуна зала Европарламента, реальное фото"),
            scene(2, "полукруг зала Европарламента с воздуха"),
            scene(3, "депутатские ряды зала Европарламента вечером"),
            scene(4, "вид из зала Европарламента на кафедру"),
        ]
        queries = [s["source_query"] for s in scenes]
        self.assertEqual(len(set(queries)), len(queries))   # every string is unique
        self.assertTrue(guards.repeated_objects(scenes))     # and still one object four times

    def test_review_flags_scene_count_and_stock(self):
        scenes = [scene(i, f"здание ведомства {i} в Москве, реальное фото") for i in range(1, 21)]
        problems = storyboard_review({"channel": "ПЛАНЕТА", "scenes": scenes}, narration_sec=690.0)
        self.assertTrue(any("scenes against a norm" in p for p in problems))
        self.assertTrue(any("stock is 0%" in p for p in problems))


class FixRoundTests(unittest.TestCase):
    def test_rewording_is_dropped_and_budget_is_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            guards.record_round(root, {"7": "здание областной администрации, реальное фото"})
            errors, drop = guards.check_round(root, {"7": "здание областной администрации реальное фото 2026"})
            self.assertIn("7", drop)
            self.assertTrue(any("rewording" in e for e in errors))

            guards.record_round(root, {"9": "пустой перрон вокзала"})
            errors, _ = guards.check_round(root, {"11": "фасад вокзала"})
            self.assertTrue(any("budget" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
