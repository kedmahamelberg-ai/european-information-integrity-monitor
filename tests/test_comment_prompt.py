import unittest

from eiim.hybrid import COMMENT_VERSION, ROOT


class CommentPromptTests(unittest.TestCase):
    def test_celebratory_emoji_rule_is_versioned_and_explicit(self):
        self.assertEqual(COMMENT_VERSION, "hybrid-comments-1.4")
        prompt = (ROOT / "prompts" / (COMMENT_VERSION + ".txt")).read_text()
        self.assertIn("Positive or celebratory reactions", prompt)
        self.assertIn("SUPPORT the video's main message", prompt)
        self.assertIn("even when they contain no words", prompt)
        self.assertIn("Flags alone", prompt)
        self.assertIn("Keep alignment separate from sentiment", prompt)


if __name__ == "__main__":
    unittest.main()
