"""Validate a saved government build before a deployment-only recovery."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def validate_source(run, jobs, artifacts, repository):
    if (run.get('head_branch') != 'main'
            or (run.get('repository') or {}).get('full_name') != repository
            or (run.get('head_repository') or {}).get('full_name') != repository
            or run.get('path') != '.github/workflows/government-news.yml'
            or run.get('status') != 'completed' or run.get('conclusion') != 'failure'):
        raise ValueError('Recovery requires a failed, completed government run from this repository main')
    collect = next((job for job in jobs if job.get('name') == 'collect'), None)
    if not collect or collect.get('status') != 'completed':
        raise ValueError('Government collection job is not complete')
    if collect.get('conclusion') != 'success':
        # Older runs combined collection and deployment in the same job.
        steps = {step.get('name'): step.get('conclusion') for step in collect.get('steps') or []}
        required = ('Collect, translate and classify official government news',
                    'Save collection checkpoint', 'Build public dashboard')
        failed = [name for name, result in steps.items() if result == 'failure']
        if (any(steps.get(name) != 'success' for name in required)
                or failed != ['Deploy updated monitor']):
            raise ValueError('Collection or build failed; it is unsafe to treat this as deployment-only')
    elif not any(job.get('name') == 'deploy' and job.get('conclusion') == 'failure' for job in jobs):
        raise ValueError('The isolated deployment job did not fail')
    candidates = [artifact for artifact in artifacts
                  if artifact.get('name') == 'github-pages' and not artifact.get('expired')]
    if len(candidates) != 1:
        raise ValueError('Recovery requires exactly one non-expired Pages artifact')
    artifact = candidates[0]
    provenance = artifact.get('workflow_run') or {}
    if provenance.get('id') != run['id'] or provenance.get('head_sha') != run['head_sha']:
        raise ValueError('Pages artifact provenance does not match the saved government run')
    return artifact['id']


def validate_archive(path):
    required = {'index.html': None, 'government-data.json': None, 'data.json': None}
    seen = set()
    total = 0
    with tarfile.open(path, 'r:*') as archive:
        for member in archive:
            name = PurePosixPath(member.name)
            if name.is_absolute() or '..' in name.parts or '\\' in member.name:
                raise ValueError('Unsafe path in saved Pages archive')
            if not (member.isdir() or member.isfile()):
                raise ValueError('Links and special files are not allowed in the saved Pages archive')
            total += member.size
            if total > 1_000_000_000:
                raise ValueError('Saved Pages archive exceeds the recovery size limit')
            normalized = str(name)
            if normalized in required:
                if normalized in seen or not member.isfile() or member.size > 25_000_000:
                    raise ValueError('Duplicate or oversized public file in saved Pages archive')
                seen.add(normalized)
                required[normalized] = archive.extractfile(member).read()
    if any(value is None for value in required.values()):
        raise ValueError('Saved Pages archive lacks required public files')
    government = json.loads(required['government-data.json'])
    research = json.loads(required['data.json'])
    items = government.get('items')
    if not government.get('as_of') or not isinstance(items, list) or not items:
        raise ValueError('Saved government snapshot is invalid or empty')
    ids = [item.get('id') for item in items]
    if not all(ids) or len(ids) != len(set(ids)):
        raise ValueError('Saved government snapshot has missing or duplicate IDs')
    if not isinstance(research.get('videos'), list):
        raise ValueError('Saved research snapshot is invalid')
    return {'government_as_of': government['as_of'], 'government_items': len(items),
            'government_sha256': hashlib.sha256(required['government-data.json']).hexdigest()}


def api(path):
    request = urllib.request.Request('https://api.github.com' + path, headers={
        'Authorization': 'Bearer ' + os.environ['GITHUB_TOKEN'],
        'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['source', 'archive'])
    parser.add_argument('archive_path', nargs='?')
    args = parser.parse_args()
    if args.phase == 'archive':
        print(json.dumps(validate_archive(args.archive_path)))
        return
    requested = os.environ.get('SOURCE_RUN_ID') or json.loads(
        (ROOT / 'ops/pages-recovery-request.json').read_text())['source_run_id']
    if not re.fullmatch(r'[1-9][0-9]*', str(requested)):
        raise ValueError('Invalid source run ID')
    repository = os.environ['GITHUB_REPOSITORY']
    base = f'/repos/{repository}/actions/runs/{requested}'
    run = api(base)
    jobs = api(base + '/jobs?filter=latest&per_page=100')['jobs']
    artifacts = api(base + '/artifacts?per_page=100')['artifacts']
    artifact_id = validate_source(run, jobs, artifacts, repository)
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        output.write(f'source_run_id={requested}\nartifact_id={artifact_id}\n')
    print(json.dumps({'source_run_id': requested, 'artifact_id': artifact_id,
                      'source_commit': run['head_sha']}))


if __name__ == '__main__':
    main()
