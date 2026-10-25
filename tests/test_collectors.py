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
             patch("assembler.collectors.search_wikimedia", side_effect=hit("wikimedia")), \
             patch("assembler.collectors.search_web", side_effect=hit("web_search")), \
             patch("assembler.collectors.search_pexels_video", side_effect=hit("pexels")):
            search_sources_detailed("запрос", limit=3)
        self.assertEqual(calls, ["dvids", "openverse", "flickr", "archive", "wikimedia", "web_search", "pexels"])

    @patch("assembler.collectors.search_openverse", return_value=[{"src": "openverse"}])
    @patch("assembler.collectors.search_wikimedia", return_value=[{"src": "wikimedia"}])
    @patch("assembler.collectors.search_archive", return_value=[])
    def test_aggregates_sources(self, archive, wikimedia, openverse):
        result = search_sources("порт", limit=2)
        self.assertEqual([x["src"] for x in result], ["openverse", "wikimedia"])

    @patch("assembler.collectors.search_dvids", side_effect=RuntimeError("offline"))
    @patch("assembler.collectors.search_openverse", return_value=[])
    @patch("assembler.collectors.search_flickr", return_value=[])
    @patch("assembler.collectors.search_wikimedia", return_value=[])
    @patch("assembler.collectors.search_archive", return_value=[])
    def test_reports_source_errors(self, archive, wikimedia, flickr, openverse, dvids):
        result = search_sources_detailed("тест")
        self.assertEqual(result["errors"][0]["source"], "dvids")
