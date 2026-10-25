import unittest
import json
import tempfile
from pathlib import Path

from assembler.srt import parse_srt
from assembler.storyboard import build_scenes
from assembler.validate import validate_payload
from assembler.dashboard import write_outputs
from assembler.storage import JobStore


class SrtPipelineTests(unittest.TestCase):
    def test_builds_contiguous_scenes(self):
        raw = """1\n00:00:00,000 --> 00:00:02,500\nПервый текст.\n\n2\n00:00:02,500 --> 00:00:06,000\nВторой текст."""
        payload = build_scenes(parse_srt(raw), "ПЛАНЕТА")
        self.assertEqual(len(payload["scenes"]), 2)
        self.assertEqual(payload["scenes"][1]["start_sec"], 2.5)
        self.assertEqual(sum(s["duration_sec"] for s in payload["scenes"]), 6.0)

    def test_rejects_empty_srt(self):
        with self.assertRaises(ValueError):
            parse_srt("not an srt")

    def test_validator_rejects_gap(self):
        payload = {"channel": "ПЛАНЕТА", "scenes": [{
            "id": 1, "text": "x", "start_sec": 1, "duration_sec": 2,
            "visual_prompt": "x", "source": "card:quote", "source_query": "x"
        }]}
        self.assertTrue(any("gap" in error for error in validate_payload(payload)))

    def test_outputs_include_resume_manifest(self):
        payload = build_scenes(parse_srt("1\n00:00:00,000 --> 00:00:01,200\nТест."), "ПЛАНЕТА")
        with tempfile.TemporaryDirectory() as directory:
            write_outputs(payload, Path(directory))
            manifest = json.loads((Path(directory) / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "dashboard_ready")
            self.assertEqual(manifest["scene_count"], 1)
            self.assertTrue((Path(directory) / "review.html").exists())

    def test_store_returns_live_state_and_writes_rejection(self):
        payload = build_scenes(parse_srt("1\n00:00:00,000 --> 00:00:01,200\nТест."), "ПЛАНЕТА")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_outputs(payload, root)
            store = JobStore(root)
            state = store.state()
            self.assertEqual(state["scenes"][0]["status"], "failed")
            store.append_log("rejections.jsonl", {"scene": "1", "reason": "test"})
            self.assertTrue((root / "rejections.jsonl").exists())

    def test_search_candidates_and_pick(self):
        payload = build_scenes(parse_srt("1\n00:00:00,000 --> 00:00:01,200\nТест."), "ПЛАНЕТА")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); write_outputs(payload, root)
            source = root / "candidate.jpg"; source.write_bytes(b"jpeg-test")
            (root / "search_options.json").write_text(json.dumps({"1": [{"path": str(source), "kind": "photo", "src": "local"}]}), encoding="utf-8")
            store = JobStore(root)
            self.assertEqual(len(store.candidates("1", "")), 1)
            self.assertTrue(store.pick_candidate("1", store.candidates("1", "")[0]).exists())

    def test_overlay_validation_clamps_values(self):
        from assembler.storage import JobStore
        value = JobStore.validate_overlay_patch({"shape": "bad", "scale": 9, "sound": "bad", "text": {"pos": "bl", "font": "bad"}})
        self.assertEqual(value["shape"], "rect")
        self.assertEqual(value["scale"], 2.4)
        self.assertEqual(value["text"]["pos"], "mc")

    def test_state_uses_manifest_source_badge(self):
        payload = build_scenes(parse_srt("1\n00:00:00,000 --> 00:00:01,200\nТест."), "ПЛАНЕТА")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); write_outputs(payload, root)
            (root / "images").mkdir(exist_ok=True); (root / "images" / "001.jpg").write_bytes(b"x")
            (root / "images" / "manifest.json").write_text(json.dumps({"1": {"source": "pexels", "kind": "video"}}), encoding="utf-8")
            state = JobStore(root).state()
            self.assertEqual(state["scenes"][0]["badge"], "pexels")
            self.assertTrue(state["scenes"][0]["is_video"])

    def test_state_contains_global_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "scenes.json").write_text(json.dumps({"scenes": []}), encoding="utf-8")
            self.assertFalse(JobStore(root).state()["approval"]["approved"])
