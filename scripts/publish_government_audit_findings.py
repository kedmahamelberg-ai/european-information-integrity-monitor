"""Keep one GitHub issue for open source-audit candidates; audit success is separate."""
import html
import json
import os
from pathlib import Path
import urllib.error
import urllib.request


REPORT = Path("government-source-audit-report.json")
TITLE = "Government source audit: open candidate findings"
API = "https://api.github.com"


def github(method, path, payload=None):
    token = os.environ["GITHUB_TOKEN"]
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(API + path, data=data, method=method,
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def find_existing_issue(repo):
    for page in range(1, 11):
        issues = github("GET", f"/repos/{repo}/issues?state=open&per_page=100&page={page}")
        for issue in issues:
            if "pull_request" not in issue and issue.get("title") == TITLE:
                return issue
        if len(issues) < 100:
            break
    return None


def clean(value):
    return html.escape(" ".join(str(value or "").split()), quote=False)


def issue_body(findings):
    lines = ["Source-audit candidates require comparison with their full official articles "
             "before a publication correction. `source_unverified` records have not passed "
             "the audit. This issue is updated by the GitHub workflow; the run artifact "
             "contains its durable checked-ID checkpoint.", ""]
    for index, (ident, finding) in enumerate(sorted(findings.items())):
        url = finding.get("source_url", "")
        block = [f"### `{clean(ident)}` · {clean(finding.get('country_code'))}",
            f"Official source: {url}",
            f"Status: `{clean(finding.get('status'))}`", ""]
        for issue in finding.get("issues", []):
            block.extend([f"- **{clean(issue.get('field'))}** ({clean(issue.get('kind'))}): "
                          f"{clean(issue.get('explanation'))}",
                          f"  - Evidence: {clean(issue.get('evidence'))}"])
        block.append("")
        if len("\n".join(lines + block)) > 58_000:
            lines.append(f"{len(findings) - index} further findings are in the latest "
                         "government-source-audit run artifact.")
            break
        lines.extend(block)
    return "\n".join(lines).strip() + "\n"


def main():
    report = json.loads(REPORT.read_text())
    findings = report["open_candidate_findings"]
    repo = os.environ["GITHUB_REPOSITORY"]
    existing = find_existing_issue(repo)
    issue_url = ""
    if findings:
        body = issue_body(findings)
        if existing:
            issue_url = existing["html_url"]
            if existing.get("body") != body:
                github("PATCH", f"/repos/{repo}/issues/{existing['number']}",
                       {"body": body})
        else:
            issue = github("POST", f"/repos/{repo}/issues",
                           {"title": TITLE, "body": body})
            issue_url = issue["html_url"]
    elif existing:
        github("PATCH", f"/repos/{repo}/issues/{existing['number']}",
               {"state": "closed", "state_reason": "completed"})

    new_ids = set(report["newly_attempted_ids"]) & set(findings)
    for ident in sorted(new_ids):
        print(f"::warning::Government source-audit candidate {ident}; "
              f"see {issue_url or 'run artifact'}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        run = f"https://github.com/{repo}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
        with open(summary, "a") as output:
            output.write(f"### Government full-source audit\n\n"
                f"Checked IDs: {report['checked_total']}; open candidate or "
                f"source-access findings: {len(findings)}.\n\n"
                f"[Run artifact]({run})"
                + (f" · [Open findings]({issue_url})" if issue_url else "") + "\n")


if __name__ == "__main__":
    main()
