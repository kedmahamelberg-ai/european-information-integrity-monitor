import unittest
from eiim.review_sampling import sample_plan


class ReviewSamplingTests(unittest.TestCase):
    def test_calibration_once_then_percentage_ceiling_and_small_pool(self):
        ids = [str(i) for i in range(143)]
        self.assertEqual(sample_plan("2026-W40", ids)["target"], 30)
        self.assertEqual(sample_plan("2026-W41", ids)["target"], 5)
        self.assertEqual(
            sample_plan("2026-W41", list(map(str, range(201))))["target"], 7
        )
        self.assertEqual(sample_plan("2026-W41", ids[:3])["target"], 3)
        self.assertEqual(sample_plan("2026-W40", [])["target"], 0)

    def test_selection_is_stable_unique_and_independent_of_input_order(self):
        ids = [str(i) for i in range(1000)]
        a = sample_plan("2026-W41", ids)
        b = sample_plan("2026-W41", list(reversed(ids)) + ids[:5])
        self.assertEqual(a, b)
        self.assertEqual(len(set(a["selected_video_ids"])), 30)
        self.assertNotEqual(
            a["selected_video_ids"], sample_plan("2026-W42", ids)["selected_video_ids"]
        )

    def test_comment_sample_is_independent_and_deduplicated(self):
        from eiim.review_sampling import comment_plan
        ids = [str(i) for i in range(315)]
        a = comment_plan('2026-W41', ids)
        self.assertEqual(a['target'], 10)
        self.assertEqual(a, comment_plan('2026-W41', ids[::-1] + ids[:10]))
        self.assertNotEqual(a['selected_comment_ids'], sample_plan('2026-W41', ids)['selected_video_ids'])
        self.assertEqual(comment_plan('2026-W41', [])['target'], 0)
        self.assertEqual(comment_plan('2026-W41', ids[:2])['target'], 2)
