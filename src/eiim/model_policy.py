"""Calendar-based Nano → Luna policy, aligned with the Observatory."""

from datetime import datetime, timezone
from functools import lru_cache
import json
from pathlib import Path


def resolve_policy(at=None, policy=None):
    policy = policy or json.loads(
        (Path(__file__).resolve().parents[2] / "config/review_models.json").read_text()
    )
    at = at or datetime.now(timezone.utc)
    if at.tzinfo is None:
        raise ValueError("Model selection needs a timezone-aware instant")
    cutoff = datetime.fromisoformat(policy["switch_at"].replace("Z", "+00:00"))
    phase = "after" if at >= cutoff else "before"
    selected = dict(policy[phase])
    selected.update(
        model_version=selected["model"],
        max_output_tokens=policy["max_output_tokens"],
        model_policy_version=policy["version"],
        model_phase=phase,
        model_switch_at=policy["switch_at"],
    )
    return selected


@lru_cache(maxsize=1)
def selected_policy():
    # A workflow process never mixes models across the midnight boundary.
    return resolve_policy()
