import unittest

from eiim.hybrid import COMMENT_VERSION, VERSION, ROOT


class CommentPromptTests(unittest.TestCase):
    def test_celebratory_emoji_rule_is_versioned_and_explicit(self):
        self.assertEqual(COMMENT_VERSION, "hybrid-comments-1.7")
        prompt = (ROOT / "prompts" / (COMMENT_VERSION + ".txt")).read_text()
        self.assertIn("equivalent positive reactions", prompt)
        self.assertIn("presumptively main_message + supports", prompt)
        self.assertIn("Words are not required", prompt)
        self.assertIn("bare national flag", prompt)
        self.assertIn("Agreement and sentiment are independent", prompt)
        self.assertIn("viewpoint_ids", prompt)
        self.assertIn("multiple_viewpoints content", prompt)
        self.assertIn("An on-topic consequence", prompt)
        self.assertIn("job losses", prompt)

    def test_human_review_scope_and_delivery_rules_are_versioned(self):
        self.assertEqual(VERSION, "hybrid-framing-1.7")
        prompt = (ROOT / "prompts" / (VERSION + ".txt")).read_text()
        self.assertIn("quirky baby-name rule", prompt)
        self.assertIn("substantive citizenship or statehood rule", prompt)
        self.assertIn("assess each independently", prompt)
        self.assertIn("scan the supplied caption sections", prompt)


if __name__ == "__main__":
    unittest.main()
