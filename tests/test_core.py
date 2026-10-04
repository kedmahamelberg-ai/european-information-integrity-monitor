import unittest, copy, json
from datetime import datetime, timezone
from eiim.core import *
from eiim.storage import MemoryStore, record
from eiim.services import Ledger, BudgetExhausted, schema
from eiim.research import emerging, agreement, validation_gate


def label():
    return {
        "othering": 2,
        "aversion": 3,
        "moralization": 2,
        "targets": [
            {
                "target_type": "institution",
                "target_name": "institutions",
                "direction": "negative",
            }
        ],
        "countries": ["NL"],
        "direction": "negative",
        "primary_narrative": "elite_betrayal",
        "secondary_narratives": [],
        "other_narrative_label": None,
        "other_narrative_explanation": None,
        "confidence": 0.8,
        "narrative_confidence": 0.7,
        "short_rationale": "Fixture only.",
    }


class WindowTests(unittest.TestCase):
    def test_requested_window(self):
        w = weekly_window(datetime.fromisoformat("2026-10-11T08:00:00+02:00"))
        self.assertEqual(w["window_start"], "2026-10-04T00:00:00+02:00")
        self.assertEqual(w["window_end"], "2026-10-10T23:59:59+02:00")

    def test_dst(self):
        for date, hours in [
            ("2026-04-05T08:00:00+02:00", 167),
            ("2026-11-01T08:00:00+01:00", 169),
        ]:
            w = weekly_window(datetime.fromisoformat(date))
            a = datetime.fromisoformat(w["window_start"]).astimezone(timezone.utc)
            b = datetime.fromisoformat(w["end_exclusive"]).astimezone(timezone.utc)
            self.assertEqual((b - a).total_seconds() / 3600, hours)

    def test_naive_rejected(self):
        with self.assertRaises(ValueError):
            weekly_window(datetime(2026, 1, 1))

    def test_midweek_completed_week(self):
        self.assertEqual(
            weekly_window(datetime.fromisoformat("2026-10-07T12:00:00+02:00"))[
                "window_start"
            ][:10],
            "2026-09-27",
        )


class MeasuresTests(unittest.TestCase):
    def test_sfi(self):
        self.assertEqual(sfi(0, 2, 4), (2, False))
        self.assertEqual(sfi(2, 2, 2), (2, True))

    def test_invalid_dimensions(self):
        for x in [-1, 5, True, 1.3, "2"]:
            with self.assertRaises(ValueError):
                sfi(x, 0, 0)

    def test_unicode_geography(self):
        self.assertIn("DE", country_matches("Deutschland news", "")[0])
        self.assertIn("UA", country_matches("Новини Україна", "")[0])
        self.assertEqual(
            country_matches("An unrelated Europeanized term", ""), ([], False)
        )
        self.assertTrue(country_matches("European Union debate", "")[1])
        self.assertFalse(term_match("skull", "UK"))

    def test_schema(self):
        x = validate_classification(label())
        self.assertAlmostEqual(x["sfi"], 7 / 3)
        for change in [
            {"confidence": float("nan")},
            {"direction": "positive"},
            {"targets": []},
            {"primary_narrative": "made_up"},
            {"primary_narrative": "other"},
        ]:
            with self.assertRaises(ValueError):
                validate_classification(label() | change)
        with self.assertRaises(ValueError):
            validate_classification("{broken")
        self.assertEqual(set(schema()["required"]), set(schema()["properties"]))

    def test_ranking(self):
        cs = [
            {"comment_id": "a", "like_count": 20, "reply_count": 0},
            {"comment_id": "b", "like_count": 0, "reply_count": 20},
            {"comment_id": "c", "like_count": 15, "reply_count": 15},
        ]
        self.assertEqual(rank_comments(cs)[0]["comment_id"], "c")

    def test_injection_requires_coherence_different_narrative(self):
        vectors = [[0, 1], [0, 1], [0, 1], [1, 0]]
        groups = coherent_clusters(vectors, 0.9, 3)
        result = injection(
            groups, [1, 0], vectors, ["corruption"], {0: ["foreign_interference"]}
        )
        self.assertEqual(result["narrative_injection_score"], 0.75)
        self.assertEqual(
            injection(groups, [1, 0], vectors, ["corruption"], {0: ["corruption"]})[
                "narrative_injection_score"
            ],
            0,
        )
        self.assertEqual(
            injection([], [1, 0], vectors, ["corruption"], {})[
                "narrative_injection_score"
            ],
            0,
        )

    def test_amplification_bounds(self):
        cs = [
            {
                "comment_id": str(i),
                "text_original": "template",
                "published_at": f"2026-10-01T10:0{i}:00+00:00",
            }
            for i in range(3)
        ]
        result = amplification(
            cs, [[0, 1]] * 3, ["corruption"] * 3, [1, 0], {"0", "1", "2"}
        )
        self.assertAlmostEqual(result["aai"], 1)
        self.assertTrue(all(0 <= v <= 1 for v in result["components"].values()))
        self.assertIsNone(amplification([], [], [], [1, 0]))

    def test_single_comment_no_burst(self):
        x = amplification(
            [
                {
                    "comment_id": "a",
                    "text_original": "hi",
                    "published_at": "2026-10-01T10:00:00Z",
                }
            ],
            [[1, 0]],
            ["none_unclear"],
            [1, 0],
        )
        self.assertEqual(x["burst_score"], 0)


class SamplingTests(unittest.TestCase):
    def frame(self):
        return [
            {
                "video_id": f"{co}-{tier}-{i}",
                "countries": [co],
                "tier": tier,
                "news_relevance": True,
            }
            for co in ["NL", "DE"]
            for tier in ["low", "medium", "high"]
            for i in range(20)
        ]

    def test_reproducible_and_probabilities(self):
        frame = self.frame()
        a = sample_frame(frame, "2026-W40")
        b = sample_frame(list(reversed(frame)), "2026-W40")
        self.assertEqual(a, b)
        self.assertEqual(sum(x["selected_for_sample"] for x in a), 20)
        for x in a:
            self.assertEqual(
                x["sampling_probability"], 0.1 if x["tier"] == "high" else 0.2
            )

    def test_outcomes_cannot_change_draw(self):
        a = self.frame()
        b = [dict(x, sfi=4, aai=1, controversy=True) for x in a]
        self.assertEqual(
            [x["video_id"] for x in sample_frame(a, "x") if x["selected_for_sample"]],
            [x["video_id"] for x in sample_frame(b, "x") if x["selected_for_sample"]],
        )

    def test_multicountry_single_draw(self):
        frame = [dict(x, countries=["DE", "NL"]) for x in self.frame()]
        a = sample_frame(frame, "x")
        self.assertEqual(len(a), len({x["video_id"] for x in a}))
        self.assertTrue(all(x["sampling_country"] in ["DE", "NL"] for x in a))

    def test_shortfall_not_replaced(self):
        a = sample_frame(self.frame()[:2], "x")
        self.assertEqual(sum(x["selected_for_sample"] for x in a), 2)
        self.assertEqual(a[0]["sampling_probability"], 1)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.s.batch({"id": "test"}, "hash")

    def test_idempotency_and_atomic_failure(self):
        r = record("comments", "test", "one", {"text": "original"})
        self.s.write("test", [r])
        self.s.write("test", [r])
        self.assertEqual(len(self.s.read("comments")), 1)
        with self.assertRaises(ValueError):
            self.s.write(
                "test",
                [
                    record("comments", "test", "two", {}),
                    record("comments", "test", "one", {"text": "changed"}),
                ],
            )
        self.assertEqual(len(self.s.read("comments")), 1)

    def test_config_freeze(self):
        with self.assertRaises(ValueError):
            self.s.batch({"id": "test"}, "different")

    def test_cost_ceiling_restart(self):
        l = Ledger(self.s, "test")
        l.reserve("llm_reserved_usd", 0.8, 1)
        with self.assertRaises(BudgetExhausted):
            Ledger(self.s, "test").reserve("llm_reserved_usd", 0.3, 1)

    def test_reservations_settle_once_and_survive_restart(self):
        ledger = Ledger(self.s, "test")
        reservation = ledger.reserve("llm_reserved_usd", 0.8, 1)
        cfg = {"input_usd_per_million": 1, "output_usd_per_million": 1}
        usage = {"prompt_tokens": 100000, "completion_tokens": 0}
        ledger.settle(reservation, usage, cfg)
        ledger.settle(reservation, usage, cfg)
        restarted = Ledger(self.s, "test")
        restarted.settle(reservation, usage, cfg)
        restarted.reserve("llm_reserved_usd", 0.8, 1)
        with self.assertRaises(BudgetExhausted):
            Ledger(self.s, "test").reserve("llm_reserved_usd", 0.11, 1)
        self.assertEqual(
            sum(e["amount"] for e in restarted.events() if e["kind"] == "llm_calls"), 2
        )

    def test_unknown_usage_keeps_reservation(self):
        ledger = Ledger(self.s, "test")
        r = ledger.reserve("llm_reserved_usd", 0.8, 1)
        ledger.settle(r, {}, {})
        with self.assertRaises(BudgetExhausted):
            ledger.reserve("llm_reserved_usd", 0.3, 1)


class ResearchTests(unittest.TestCase):
    def test_emerging_consecutive_weeks(self):
        items = [
            {"id": str(i), "label": "new label", "week_start": d}
            for i, d in enumerate(
                [
                    "2026-09-13T00:00:00+02:00",
                    "2026-09-20T00:00:00+02:00",
                    "2026-09-27T00:00:00+02:00",
                ]
            )
        ]
        self.assertTrue(
            emerging(items, [[1, 0]] * 3)[0]["candidate_emerging_narrative"]
        )
        items[-1]["week_start"] = "2026-10-11T00:00:00+02:00"
        self.assertFalse(
            emerging(items, [[1, 0]] * 3)[0]["candidate_emerging_narrative"]
        )

    def test_no_fabricated_agreement_or_launch(self):
        self.assertIsNone(agreement([])["dimension_agreement"])
        self.assertFalse(validation_gate([], "v")["passed"])


if __name__ == "__main__":
    unittest.main()
