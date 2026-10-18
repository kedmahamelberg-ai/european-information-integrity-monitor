"""Discovery-frame, geography and duplicate-comment regression checks."""

import unittest
from datetime import datetime
from unittest.mock import patch

from eiim.core import config, country_matches, rank_comments, tourism_only, weekly_window
from eiim.services import YouTube


class DiscoveryCueTests(unittest.TestCase):
    def test_major_city_cues_cover_monitored_countries(self):
        countries = config("countries")["countries"]
        self.assertEqual(len(countries), 51)
        self.assertEqual(next(c for c in countries if c["iso2"] == "PT")["major_city_cues"],
                         ["Lisbon", "Porto", "Braga"])
        self.assertEqual(next(c for c in countries if c["iso2"] == "FR")["major_city_cues"],
                         ["Paris", "Marseille", "Lyon"])
        self.assertTrue(all(1 <= len(c["major_city_cues"]) <= 3 for c in countries))
        self.assertIn("PT", country_matches("Protesto no Porto", "")[0])
        self.assertIn("FR", country_matches("Manifestation à Marseille", "")[0])

    def test_tourism_filter_preserves_public_affairs(self):
        self.assertTrue(tourism_only("Porto walking tour 4K"))
        self.assertTrue(tourism_only("Passeio por Porto em 4K"))
        self.assertTrue(tourism_only("Paris travel guide"))
        self.assertFalse(tourism_only("Porto walking tour after housing protest"))
        self.assertFalse(tourism_only("Tourism tax protests in Lisbon"))

    def test_one_whole_week_search_per_country_and_deduplicated_ids(self):
        geography = {
            "countries": [
                {"country_name": "France", "english_demonym": "French", "local_names": [],
                 "variants": [], "major_city_cues": ["Paris", "Marseille", "Lyon"]},
                {"country_name": "Portugal", "english_demonym": "Portuguese", "local_names": [],
                 "variants": [], "major_city_cues": ["Lisbon", "Porto", "Braga"]},
            ]
        }
        yt = object.__new__(YouTube)
        yt.cfg = {"search_pages_per_query": 1, "search_page_size": 50}
        calls = []

        def fake_get(resource, **params):
            calls.append((resource, params))
            return {"items": [
                {"id": {"videoId": "same-video"}, "snippet": {"title": "Porto protest", "description": ""}},
                {"id": {"videoId": "travel-video"}, "snippet": {"title": "Porto walking tour 4K", "description": ""}},
            ], "nextPageToken": "another-page"}

        yt.get = fake_get
        window = weekly_window(datetime.fromisoformat("2026-10-18T08:00:00+02:00"))
        with patch("eiim.services.config", return_value=geography):
            ids = yt.discover(window)
        self.assertEqual(ids, ["same-video"])
        self.assertEqual(len(calls), 3)  # Two countries and the unchanged EU stratum.
        self.assertTrue(all(p["order"] == "relevance" for _, p in calls))
        self.assertTrue(all("pageToken" not in p for _, p in calls))
        self.assertTrue(all(p["publishedAfter"].startswith("2026-10-10T21:59:59") for _, p in calls))
        self.assertTrue(all(p["publishedBefore"].startswith("2026-10-17T22:00:00") for _, p in calls))
        self.assertIn('"Porto"', calls[1][1]["q"])

    def test_duplicate_comment_ids_are_not_retained_twice(self):
        yt = object.__new__(YouTube)
        yt.cfg = {"comment_pool_limit": 100}
        comment = {"id": "comment-1", "snippet": {
            "textOriginal": "Agree", "likeCount": 2,
            "publishedAt": "2026-10-17T10:00:00Z",
        }}
        yt.get = lambda resource, **params: {"items": [
            {"snippet": {"topLevelComment": comment, "totalReplyCount": 0}},
            {"snippet": {"topLevelComment": comment, "totalReplyCount": 0}},
        ]}
        pool, status = yt.comments("video-1")
        self.assertEqual(status, "pool_exhausted")
        self.assertEqual(len(pool), 1)
        self.assertEqual(len(rank_comments(pool + pool)), 1)


if __name__ == "__main__":
    unittest.main()
