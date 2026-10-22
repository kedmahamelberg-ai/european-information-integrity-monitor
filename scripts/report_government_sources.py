"""Summarize the collector's source evidence in the Actions run."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "build/government-source-diagnostics.json"


def summary(report):
    sources = sorted(report["sources"], key=lambda row: row["country_code"])
    lines = ["## Government source access", "",
             f"Attempted {report['attempted_sources']} ready countries; "
             f"skipped {len(report['skipped_after_early_success'])} checked earlier today.", ""]
    failures = [row for row in sources if row["status"] != "discovered"]
    if not failures:
        lines.append("Every attempted source was reachable. A source omitted from this pass may have been checked earlier today.")
    else:
        lines.extend(["| Country | Runner result | HTTP | Interpretation |", "| --- | --- | --- | --- |"])
        for row in failures:
            lines.append(f"| {row['country']} | {row.get('error', 'unknown')} | "
                         f"{row.get('http_status') or '—'} | {row.get('error_category', 'unknown')} |")
    article_failures = report.get("article_failures", [])
    if article_failures:
        lines.extend(["", f"Full article retrieval failed for {len(article_failures)} item(s):", "",
                      "| Country | HTTP | Interpretation | Official article |",
                      "| --- | --- | --- | --- |"])
        for row in article_failures:
            lines.append(f"| {row['country_code']} | {row.get('http_status') or '—'} | "
                         f"{row.get('error_category', 'unknown')} | {row['url']} |")
    lines.extend(["", "These labels describe this runner's observation. To distinguish blocking "
                  "from an outage, compare the exact official section URL at the same time from an "
                  "independent network. A successful second fetch supports an egress or access issue; "
                  "a matching failure needs the publisher's status or another independent check.", ""])
    return "\n".join(lines)


def main():
    if REPORT.exists():
        message = summary(json.loads(REPORT.read_text()))
    else:
        message = "## Government source access\n\nCollection stopped before its source report was written. Inspect the failed step.\n"
    print(message)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as handle:
            handle.write(message)


if __name__ == "__main__":
    main()
