"""Regression for YouTube metadata that PostgreSQL JSONB cannot store."""
import io
import json
import os
import unittest
from unittest.mock import Mock, patch

from eiim.services import YouTube
from eiim.storage import MemoryStore


class YouTubeNulTests(unittest.TestCase):
    def test_nested_nul_is_removed_before_cached_write(self):
        store = MemoryStore()
        body = {"items": [{"snippet": {"title": "A\x00B", "description": "C\x00D"}}]}
        response = io.BytesIO(json.dumps(body).encode())
        with patch.dict(os.environ, {"YOUTUBE_API_KEY": "private-test-key"}), \
             patch("eiim.services.urllib.request.urlopen", return_value=response):
            result = YouTube(store, "2026-W42", Mock()).get("videos", id="abcdefghijk")
        self.assertEqual(result["items"][0]["snippet"]["title"], "AB")
        saved = store.read("search_requests", "2026-W42")
        self.assertEqual(len(saved), 1)
        self.assertNotIn("\\u0000", json.dumps(saved))


if __name__ == "__main__":
    unittest.main()
