import copy
import unittest
from eiim.hybrid import validate_comments
from eiim.hybrid_review import validate_review, media_evidence
from test_hybrid import label, document
import test_hybrid


class FeedbackTests(unittest.TestCase):
    def test_speaker_praise_is_not_message_agreement(self):
        c = label()["comments"][0]
        c.update(
            response_focus="speaker",
            alignment="supports",
            sentiment="positive",
            sentiment_target="Speaker delivery",
        )
        with self.assertRaisesRegex(ValueError, "Speaker/presentation"):
            validate_comments({"comments": [c]}, document())
        c.update(alignment="no_position", stance_target="")
        validate_comments({"comments": [c]}, document())

    def test_target_criticism_can_align_with_critical_message(self):
        c = label()["comments"][0]
        c.update(
            response_focus="video_target",
            alignment="supports",
            sentiment="negative",
            sentiment_target="Government housing performance",
        )
        validate_comments({"comments": [c]}, document())

    def test_not_related_can_be_corrected_to_related(self):
        item, row = test_hybrid.HumanReviewTests().review()
        row = copy.deepcopy(row)
        row["payload"]["label"].update(relevance="not_related", topics=[], roles=[])
        for e in row["payload"]["label"]["execution"]:
            e["status"] = "not_applicable"
        from eiim.core import digest
        from eiim.hybrid_review import video_values

        row["payload_hash"] = digest(row["payload"])
        item.update(
            queue_hash=row["payload_hash"],
            human_label=video_values(row["payload"]["label"]),
        )
        item["human_label"].update(
            relevance="related", topics=["political_institutions"]
        )
        item["decisions"].update(relevance="disagree", topics="disagree")
        for e in row["payload"]["label"]["execution"]:
            k = "execution:" + e["category"]
            item["human_label"][k] = "not_observable"
            item["decisions"][k] = "disagree"
        validate_review(item, row)
        item["human_label"]["execution:entertainment"] = "not_applicable"
        with self.assertRaises(ValueError):
            validate_review(item, row)

    def test_music_cues_are_observations_not_mnemonic_inferences(self):
        result = media_evidence(
            {},
            {
                "transcript_english": [
                    {"start": 2, "text": "[Music]"},
                    {"start": 4, "text": "Water"},
                ]
            },
        )
        self.assertEqual(len(result["music_caption_cues"]), 1)
        self.assertEqual(result["audio_analysis"], "not_performed")
        self.assertNotIn("mnemonic_devices", result)
        self.assertEqual(media_evidence({}, {})["music_caption_cues"], [])
