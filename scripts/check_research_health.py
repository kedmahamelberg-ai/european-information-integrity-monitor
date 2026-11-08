"""Check that the completed Amsterdam research week reached the public site."""

import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

DATA_URL = "https://monitor.hamelberg-ai.com/data.json"


def expected_batch(at):
    local = at.astimezone(ZoneInfo("Europe/Amsterdam")).date()
    last_saturday = local - timedelta(days=(local.weekday() - 5) % 7)
    year, week, _ = last_saturday.isocalendar()
    return f"{year}-W{week:02d}"


def check(data, at):
    batch = expected_batch(at)
    if not any(row.get("id") == batch for row in data.get("batches", [])):
        raise ValueError(f"{batch}: completed weekly sample is missing from the public site")
    sampled = sum(row.get("batch") == batch for row in data.get("inventory", []))
    if sampled == 0:
        raise ValueError(f"{batch}: no sampled videos reached the public site")
    classified = sum(
        row.get("batch") == batch and bool(row.get("label"))
        for row in data.get("videos", [])
    )
    if classified == 0:
        raise ValueError(
            f"{batch}: {sampled} videos sampled but none classified; "
            "check transcript recovery, saved-text classification and publication"
        )
    return f"{batch}: {classified} classified of {sampled} sampled sources"


def main():
    request = urllib.request.Request(
        f"{DATA_URL}?health={int(datetime.now(timezone.utc).timestamp())}",
        headers={"Cache-Control": "no-cache", "User-Agent": "EIIM-research-health/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.load(response)
    try:
        print(check(data, datetime.now(timezone.utc)))
    except ValueError as error:
        print(f"::error::{error}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
