"""Publish new or changed archive files together in a GitHub-verified commit."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys


def save(checkout):
    paths = subprocess.check_output(
        ["git", "ls-files", "--modified", "--others", "--exclude-standard", "-z", "--", "editions/"],
        cwd=checkout,
    ).decode().split("\0")
    additions = [
        {"path": path, "contents": base64.b64encode((checkout / path).read_bytes()).decode("ascii")}
        for path in paths if path
    ]
    if not additions:
        return
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, cwd=checkout).strip()
    mutation = """mutation ($input: CreateCommitOnBranchInput!) {
      createCommitOnBranch(input: $input) { commit { oid } }
    }"""
    ref_endpoint = f"repos/{os.environ['GITHUB_REPOSITORY']}/git/ref/heads/field-wire-editions"
    branch_id = subprocess.check_output(["gh", "api", ref_endpoint, "--jq", ".node_id"], text=True).strip()
    variables = {"input": {
        "branch": {"id": branch_id},
        "expectedHeadOid": head,
        "message": {"headline": "Publish Field Wire edition"},
        "fileChanges": {"additions": additions},
    }}
    subprocess.run(["gh", "api", "graphql", "--input", "-", "--silent"], check=True, text=True,
                   input=json.dumps({"query": mutation, "variables": variables}))


if __name__ == "__main__":
    save(Path(sys.argv[1]))
