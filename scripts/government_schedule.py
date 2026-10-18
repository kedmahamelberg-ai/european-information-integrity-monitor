"""Plan the daily 15:00 Amsterdam collection and its automatic retries."""
import argparse
import ast
import datetime as dt
import json
import os
from pathlib import Path
import time
from zoneinfo import ZoneInfo

AMSTERDAM = ZoneInfo("Europe/Amsterdam")


def schedule_plan(now, event):
    if event != "schedule":
        return {"enabled": "true", "until": "", "wait_seconds": 0}
    local = now.astimezone(AMSTERDAM)
    target = local.replace(hour=15, minute=0, second=0, microsecond=0)
    wait = max(0, (target - local).total_seconds())
    # Only the 14:47 warm-up may wait; never hold a runner for hours.
    return {"enabled": "true" if wait <= 900 else "false",
            "until": target.isoformat(), "wait_seconds": wait if wait <= 900 else 0}


def collection_mode(state, ready_codes, until):
    if not until:
        return "collect"
    target = dt.datetime.fromisoformat(until)
    cursors = state.get("source_cursors", {})
    for code in ready_codes:
        try:
            cursor = dt.datetime.fromisoformat(cursors[code])
            if cursor.tzinfo is None or cursor < target:
                return "collect"
        except (KeyError, TypeError, ValueError):
            return "collect"
    # The collector's classify-only path recreates the public files and retries
    # any saved pending classifications, without requesting source archives.
    return "classify-only" if ready_codes else "collect"


def ready_codes(path):
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "COLLECTOR_READY_CODES"
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise ValueError("Collector ready-country allowlist was not found")


def output(values):
    with open(os.environ["GITHUB_OUTPUT"], "a") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["prepare", "collect"])
    args = parser.parse_args()
    if args.phase == "prepare":
        plan = schedule_plan(dt.datetime.now(dt.timezone.utc), os.environ.get("GITHUB_EVENT_NAME"))
        print(f"Daily schedule: {plan}", flush=True)
        if plan["enabled"] == "true" and plan["wait_seconds"]:
            target = dt.datetime.fromisoformat(plan["until"])
            while (remaining := (target - dt.datetime.now(dt.timezone.utc)).total_seconds()) > 0:
                time.sleep(min(30, remaining))
        output({key: plan[key] for key in ("enabled", "until")})
    else:
        root = Path(__file__).resolve().parents[1]
        state_path = root / "data/government_state.json"
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        codes = ready_codes(root / "scripts/collect_government_news.py")
        mode = collection_mode(state, codes, os.environ.get("DAILY_UNTIL", ""))
        print(f"Daily collection mode: {mode}; {len(codes)} working countries", flush=True)
        output({"mode": mode})


if __name__ == "__main__":
    main()
