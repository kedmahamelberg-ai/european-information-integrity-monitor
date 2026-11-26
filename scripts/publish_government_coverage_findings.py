"""Maintain one issue for actual archive gaps and unverified sources."""
import json
import os
from pathlib import Path

from publish_government_audit_findings import github

TITLE='Government archive coverage: missing or unverified sources'


def find_issue(repo):
    for page in range(1,11):
        rows=github('GET',f'/repos/{repo}/issues?state=open&per_page=100&page={page}')
        found=next((row for row in rows if row.get('title')==TITLE and 'pull_request' not in row),None)
        if found:return found
        if len(rows)<100:return None


def body(report,check=None):
    lines=['These official source archives have not passed complete acquisition. A failed request does not prove that the publisher is offline.',
           'Saved pending classifications and the separate full-article editorial audit are different checks.','']
    if check and check.get('verification_error'):
        lines.extend(['### Live publication verification',check['verification_error'],''])
    for row in sorted(report.get('sources',[]),key=lambda x:x['country_code']):
        if row['status']=='complete':continue
        lines.extend([f"### {row['country_code']} — {row['country']}",row['source_url'],
                      f"Status: {row['status']}",str(row.get('error') or ''),''])
        lines.extend(row.get('missing_urls',[]))
    return '\n'.join(lines).strip()+'\n'


def main():
    path=Path('build/government-source-coverage.json')
    if not path.exists():
        print('No archive proof exists for this run; inspect the failed collection step.')
        return
    report=json.loads(path.read_text());repo=os.environ['GITHUB_REPOSITORY'];issue=find_issue(repo)
    check_path=Path('government-source-coverage-check.json')
    check=json.loads(check_path.read_text()) if check_path.exists() else {'verification_error':'The live archive verification did not produce a result.'}
    unresolved=bool(check.get('verification_error')) or any(row['status']!='complete' for row in report['sources'])
    if unresolved:
        text=body(report,check)
        if issue:
            if issue.get('body')!=text:github('PATCH',f"/repos/{repo}/issues/{issue['number']}",{'body':text})
        else:github('POST',f'/repos/{repo}/issues',{'title':TITLE,'body':text})
    elif issue:github('PATCH',f"/repos/{repo}/issues/{issue['number']}",{'state':'closed','state_reason':'completed'})


if __name__=='__main__':main()
