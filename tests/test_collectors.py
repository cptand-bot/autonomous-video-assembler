import unittest
from unittest.mock import patch

from assembler.collectors import search_sources, search_sources_detailed


class CollectorTests(unittest.TestCase):
    def test_source_waterfall_order(self):
        calls = []
        def hit(name):
            def fn(query, limit):
                calls.append(name)
                return []
            return fn
        with patch("assembler.collectors.search_dvids", side_effect=hit("dvids")), \
             patch("assembler.collectors.search_openverse", side_effect=hit("openverse")), \
             patch("assembler.collectors.search_flickr", side_effect=hit("flickr")), \
             patch("assembler.collectors.search_archive", side_effect=hit("archive")), \
             patch("assembler.collectors.search_yandex", side_effect=hit("yandex")), \
             patch("assembler.collectors.search_ddg_images", side_effect=hit("ddg")), \
             patch("assembler.collectors.search_google", side_effect=hit("google")), \
             patch("assembler.collectors.search_pexels_video", side_effect=hit("pexels")):
            search_sources_detailed("запрос", limit=3)
        self.assertEqual(calls, ["yandex", "google", "ddg", "archive"])

    @patch("assembler.collectors._get_json", return_value={"results": [{"url": "https://x/image.jpg", "license": "cc0", "creator": "Author"}]})
    def test_openverse_preserves_license_metadata(self, get_json):
        result = __import__("assembler.collectors", fromlist=["search_openverse"]).search_openverse("test", 1)
        self.assertEqual(result[0]["license"], "cc0")
        self.assertEqual(result[0]["creator"], "Author")

    @patch("assembler.collectors.search_openverse", return_value=[{"src": "openverse"}])
    @patch("assembler.collectors.search_yandex", return_value=[])
    @patch("assembler.collectors.search_ddg_images", return_value=[])
    @patch("assembler.collectors.search_google", return_value=[])
    @patch("assembler.collectors.search_archive", return_value=[])
    def test_aggregates_sources(self, archive, google, ddg, yandex, openverse):
        result = search_sources("порт", limit=2)
        self.assertEqual([x["src"] for x in result], [])

    @patch("assembler.collectors.search_dvids", side_effect=RuntimeError("offline"))
    @patch("assembler.collectors.search_openverse", return_value=[])
    @patch("assembler.collectors.search_flickr", return_value=[])
    @patch("assembler.collectors.search_yandex", side_effect=RuntimeError("offline"))
    @patch("assembler.collectors.search_google", return_value=[])
    @patch("assembler.collectors.search_archive", return_value=[])
    def test_reports_source_errors(self, archive, google, yandex, flickr, openverse, dvids):
        result = search_sources_detailed("тест")
        self.assertEqual(result["errors"][0]["source"], "yandex")
