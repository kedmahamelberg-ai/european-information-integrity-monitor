import unittest

from eiim.hybrid import COMMENT_VERSION, ROOT


class CommentPromptTests(unittest.TestCase):
    def test_celebratory_emoji_rule_is_versioned_and_explicit(self):
        self.assertEqual(COMMENT_VERSION, "hybrid-comments-1.6")
        prompt = (ROOT / "prompts" / (COMMENT_VERSION + ".txt")).read_text()
        self.assertIn("equivalent positive reactions", prompt)
        self.assertIn("presumptively main_message + supports", prompt)
        self.assertIn("Words are not required", prompt)
        self.assertIn("bare national flag", prompt)
        self.assertIn("Agreement and sentiment are independent", prompt)
        self.assertIn("viewpoint_ids", prompt)
        self.assertIn("multiple_viewpoints content", prompt)


if __name__ == "__main__":
    unittest.main()
