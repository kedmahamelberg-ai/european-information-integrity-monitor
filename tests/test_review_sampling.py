import unittest
from eiim.review_sampling import sample_plan


class ReviewSamplingTests(unittest.TestCase):
    def test_calibration_once_then_percentage_ceiling_and_small_pool(self):
        ids = [str(i) for i in range(143)]
        self.assertEqual(sample_plan("2026-W40", ids)["target"], 30)
        self.assertEqual(sample_plan("2026-W41", ids)["target"], 9)
        self.assertEqual(
            sample_plan("2026-W41", list(map(str, range(201))))["target"], 13
        )
        self.assertEqual(sample_plan("2026-W41", ids[:3])["target"], 3)
        self.assertEqual(sample_plan("2026-W40", [])["target"], 0)

    def test_selection_is_stable_unique_and_independent_of_input_order(self):
        ids = [str(i) for i in range(1000)]
        a = sample_plan("2026-W41", ids)
        b = sample_plan("2026-W41", list(reversed(ids)) + ids[:5])
        self.assertEqual(a, b)
        self.assertEqual(len(set(a["selected_video_ids"])), 60)
        self.assertNotEqual(
            a["selected_video_ids"], sample_plan("2026-W42", ids)["selected_video_ids"]
        )

    def test_video_sample_represents_comment_bearing_clusters(self):
        ids = [str(i) for i in range(143)]
        comments = {vid: ([f"c-{vid}"] if int(vid) < 10 else []) for vid in ids}
        plan = sample_plan("2026-W41", ids, comments_by_video=comments)
        self.assertEqual(plan["target"], 9)
        self.assertTrue(any(comments[vid] for vid in plan["selected_video_ids"]))
        self.assertTrue(any(not comments[vid] for vid in plan["selected_video_ids"]))

    def test_comments_follow_selected_video_clusters(self):
        from eiim.review_sampling import linked_comment_plan
        ids = [f"v{i}" for i in range(100)]
        comments = {vid: [f"{vid}-a", f"{vid}-b"] for vid in ids}
        video_plan = sample_plan("2026-W41", ids, comments_by_video=comments)
        plan = linked_comment_plan("2026-W41", video_plan, comments)
        expected = sorted(
            cid
            for vid in video_plan["selected_video_ids"]
            for cid in comments[vid]
        )
        self.assertEqual(plan["selected_comment_ids"], expected)
        self.assertEqual(plan["target"], len(expected))
        self.assertEqual(plan["population"], 200)
