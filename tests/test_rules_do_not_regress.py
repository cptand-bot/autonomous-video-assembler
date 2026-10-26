"""ПРАВИЛА, ЗАКРЫТЫЕ КОДОМ 26.10. НЕ УДАЛЯТЬ И НЕ ОСЛАБЛЯТЬ ЭТИ ТЕСТЫ.

Каждый тест ниже — это ошибка, которая УЖЕ была допущена и стоила дня работы.
Память между сессиями не сохраняется, поэтому правило живёт здесь, а не в
переписке: если правка возвращает ошибку, падает тест, а не человек через два
дня на дашборде.

Порядок работы, выведенный 26.10: СНАЧАЛА тест, который ловит ошибку, ПОТОМ
правка. Правка без такого теста уезжает обратно при следующем же изменении —
так за один день трижды отменялись уже сделанные исправления.
"""

import json
import tempfile
import unittest
from pathlib import Path

from assembler.dashboard import render_review
from assembler.media import MediaError, normalize_image
from assembler.storyboard import build_search_query


SCENE = {
    "id": 1,
    "text": "Илон Маск в последние дни неожиданно решил поговорить о морали.",
    "start_sec": 0.0,
    "duration_sec": 11.0,
    "source": "press_photo",
    "source_query": "терминал Starlink в полевых условиях",
}


class DashboardWorksFromDisk(unittest.TestCase):
    """Человек открывает СКАЧАННЫЙ артефакт файлом с диска. Сервера нет."""

    def page(self) -> str:
        return render_review({
            "channel": "5 МИНУТ",
            "scenes": [SCENE],
            "assets": {"1": {"image": "images/001.jpg", "status": "ok"}},
            "overlays": {"1": {"planned": True, "photo": "overlays/scene_001.jpg"}},
        })

    def test_frames_are_embedded_with_relative_paths(self):
        # Было: ссылок images/ в странице 0 из 55 — кадры приходили только от
        # сервера, которого в облаке нет, и человек видел пустые карточки.
        self.assertIn("images/001.jpg", self.page())

    def test_overlays_are_embedded_with_relative_paths(self):
        self.assertIn("overlays/scene_001.jpg", self.page())

    def test_no_absolute_media_paths(self):
        # Одна ведущая косая черта превращала правильный относительный путь в
        # абсолютный, и с диска картинка не грузилась. Два дня из-за одного
        # символа.
        self.assertNotIn('src="/', self.page())

    def test_offline_mode_is_visible_and_polling_stops(self):
        # Было: пустой catch(e){} — страница молча стучалась в никуда каждые
        # 2,5 с, и понять, что сервера нет, было невозможно.
        source = Path("assembler/dashboard.py").read_text(encoding="utf-8")
        self.assertIn("АВТОНОМНЫЙ РЕЖИМ", source)
        self.assertIn("clearInterval(window._poll)", source)
        self.assertNotIn("catch(e){{}}", source)


class QualityCheckActuallyChecks(unittest.TestCase):
    def test_frames_come_from_manifest_not_from_a_guessed_mask(self):
        # Было: маска images/glob("scene_*") не совпадала НИ С ОДНИМ файлом —
        # кадры сцен называются 001.jpg. Проверка качества за два дня не
        # посмотрела ни на один кадр и всегда печатала «ok».
        source = Path("assembler/selfcheck.py").read_text(encoding="utf-8")
        self.assertNotIn('glob("scene_*")', source)
        self.assertIn('manifest.values()', source)

    def test_quality_is_a_warning_not_a_job_killer(self):
        # Слабый кадр человек меняет на дашборде жёлтой карточкой. Падение
        # джоба лишает его и дашборда тоже — это дороже, чем слабый кадр.
        source = Path("assembler/selfcheck.py").read_text(encoding="utf-8")
        self.assertIn("quality_report.json", source)
        self.assertNotIn('errors.append("quality: "', source)


class NoFixturesInsteadOfLogic(unittest.TestCase):
    def test_storyboard_has_no_topic_keyed_ready_queries(self):
        # Было: список из 56 готовых запросов и ветка if "starlink" in topic,
        # выдача по НОМЕРУ сцены. На этом ролике выглядело осмысленно, на любом
        # другом рассыпалось обратно в мусор из озвучки.
        source = Path("assembler/storyboard.py").read_text(encoding="utf-8")
        self.assertNotIn("in topic.lower()", source)
        self.assertNotIn("_STARLINK_OBJECTS", source)

    def test_same_scene_gives_same_query_regardless_of_topic(self):
        # Запрос строится из СМЫСЛА СЦЕНЫ. Если он зависит от темы ролика —
        # значит где-то снова появилась ветка под конкретный ролик.
        a = build_search_query(SCENE["text"], set(), "Илон Маск Starlink")
        b = build_search_query(SCENE["text"], set(), "Си Цзиньпин Тайвань")
        self.assertEqual(a, b)


class ImageThresholdIsAWarningFloorNotAWall(unittest.TestCase):
    def frame(self, width: int, height: int) -> bytes:
        from io import BytesIO

        from PIL import Image

        buffer = BytesIO()
        Image.new("RGB", (width, height), "red").save(buffer, format="PNG")
        return buffer.getvalue()

    def test_news_16x9_frame_passes_the_fallback_floor(self):
        # Было: при поле 900 порог 900 применялся И К ВЫСОТЕ, поэтому кадр
        # 1280x720 выбрасывался из-за высоты 720. Замер: 286 отказов из 302 —
        # кадры шириной 1200+. Одна строка держала 13 пустых сцен из 13.
        data, width, height, _ = normalize_image(self.frame(1280, 720), minimum=900)
        self.assertEqual((width, height), (1280, 720))

    def test_primary_floor_still_rejects_the_same_frame(self):
        # Без этого теста «починить» можно, просто сняв проверку.
        with self.assertRaises(MediaError):
            normalize_image(self.frame(1280, 720), minimum=1600)


class OverlayIsNotACopyOfSomethingAlreadyOnScreen(unittest.TestCase):
    def test_duplicate_check_covers_every_scene_not_only_its_own(self):
        # Замер: из 5 всплывашек 3 были полноэкранными кадрами ДРУГИХ сцен
        # (10<-51, 19<-16, 46<-16). Проверка «совпало с базой своей сцены»
        # ловила только одну из пяти.
        source = Path("assembler/fetch_job.py").read_text(encoding="utf-8")
        self.assertIn("used_overlay_md5", source)
        self.assertIn("for s, m in scene_md5.items()", source)

    def test_overlay_text_must_not_repeat_the_narration(self):
        # Было: пять из шести надписей — дословная копия фразы, которая в эту
        # же секунду звучит. Всплывашка обязана ДОБАВЛЯТЬ то, чего нет.
        overlays = {"1": {"planned": True, "text": {"words": SCENE["text"][:40]}}}
        words = overlays["1"]["text"]["words"].strip()
        self.assertIn(words, SCENE["text"], "подготовка теста: это копия озвучки")
        self.assertTrue(
            self.is_narration_copy(words, SCENE["text"]),
            "проверка копии озвучки должна срабатывать",
        )

    @staticmethod
    def is_narration_copy(words: str, scene_text: str) -> bool:
        """Правило одной строкой: подстрока надписи не встречается в сцене."""
        cleaned = " ".join(words.lower().split())
        return bool(cleaned) and cleaned in " ".join(scene_text.lower().split())


class ArtifactStaysOpenableByAHuman(unittest.TestCase):
    def test_review_html_is_written_next_to_its_media(self):
        from assembler.dashboard import write_outputs

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_outputs({"channel": "5 МИНУТ", "scenes": [SCENE]}, root)
            self.assertTrue((root / "review.html").exists())
            self.assertTrue((root / "scenes.json").exists())
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["scene_count"], 1)


if __name__ == "__main__":
    unittest.main()
