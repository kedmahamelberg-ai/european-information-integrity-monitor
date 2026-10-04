"""Synthetic live regression probes, not an independent human benchmark."""

from .core import digest, now
from .storage import record
from .reclassification import (
    configure_candidate,
    classify_document,
    evidence_input,
    DIMENSIONS,
    VERSION,
)

CASES = [
    (
        "service_failure",
        "The municipal office has not issued permits for six weeks. Residents need a clear timetable.",
        "scored",
        [(0, 0)] * 3,
    ),
    (
        "missing_government",
        "There is no functioning council after the resignations. Essential services are interrupted.",
        "scored",
        [(0, 0)] * 3,
    ),
    (
        "social_distance",
        "Supporters of the governing party seem to inhabit a world I cannot understand.",
        "scored",
        [(1, 3), (0, 0), (0, 0)],
    ),
    (
        "mild_dislike",
        "I find those governing-party supporters rather irritating.",
        "scored",
        [(0, 0), (1, 2), (0, 0)],
    ),
    (
        "integrity",
        "The ministers deliberately deceive the public to enrich themselves.",
        "scored",
        [(0, 0), (0, 1), (2, 3)],
    ),
    (
        "negative_control_reporting",
        "Police are investigating claims of corruption at the town hall. No findings have been issued.",
        "scored",
        [(0, 0)] * 3,
    ),
    (
        "negative_control_rejection",
        "Calling our political opponents subhuman is unacceptable. They deserve the same rights as us.",
        "scored",
        [(0, 0)] * 3,
    ),
    (
        "severe_combination",
        "Opposition supporters are subhuman vermin, evil to the core. I hate every one of them.",
        "scored",
        [(3, 4), (3, 4), (3, 4)],
    ),
    ("sparse_title", "The new parliament", "insufficient_evidence", [None] * 3),
    (
        "positive_praise",
        "The council is honest and compassionate, and I admire its members.",
        "scored",
        [(0, 0)] * 3,
    ),
]


def run_evaluation(store, batch, classifier=None):
    from .services import Classifier, Ledger, ClassificationUnavailable

    model = configure_candidate(
        classifier or Classifier(store, batch, Ledger(store, batch))
    )
    rows = []
    for name, text, status, ranges in CASES:
        document = evidence_input({"title": text}, {})
        try:
            result = classify_document(model, document)["parsed"]
            checks = [result["assessment_status"] == status]
            for k, expected in zip(DIMENSIONS, ranges):
                value = result[k]
                checks.append(
                    value is None
                    if expected is None
                    else type(value) is int and expected[0] <= value <= expected[1]
                )
            rows.append(
                dict(
                    case=name,
                    passed=all(checks),
                    expected_status=status,
                    expected_ranges=ranges,
                    observed_status=result["assessment_status"],
                    scores={k: result[k] for k in DIMENSIONS},
                )
            )
        except ClassificationUnavailable:
            rows.append(dict(case=name, passed=False, error="model_output_unavailable"))
    report = dict(
        classifier_version=VERSION,
        evaluation_type="synthetic_regression_not_human_validation",
        passed=sum(r["passed"] for r in rows),
        total=len(rows),
        cases=rows,
        independent_holdout=False,
        generated_at=now(),
    )
    store.write(
        batch,
        [
            record(
                "pipeline_runs",
                batch,
                f"{batch}:evidence-evaluation:" + digest(report),
                {"evidence_evaluation": report},
            )
        ],
    )
    return report
