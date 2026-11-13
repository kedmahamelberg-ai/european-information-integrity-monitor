"""Catch reusable-workflow token permission mismatches before GitHub schedules them."""

from pathlib import Path
import re
import sys


WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
PERMISSION_LEVEL = {"none": 0, "read": 1, "write": 2}
CALL = re.compile(r"^    uses: \./\.github/workflows/([\w.-]+\.ya?ml)\s*$")
JOB = re.compile(r"^  ([\w-]+):\s*$")


def permissions(lines, start, stop, indent):
    """Read a permissions mapping at one YAML indentation level."""
    prefix = " " * indent
    for index in range(start, stop):
        if lines[index] != prefix + "permissions:":
            continue
        grants = {}
        for entry in lines[index + 1 : stop]:
            if not entry.strip():
                continue
            if len(entry) - len(entry.lstrip()) <= indent:
                break
            match = re.fullmatch(rf"{prefix}  ([\w-]+): (none|read|write)\s*", entry)
            if not match:
                raise ValueError(f"Unsupported permissions entry: {entry.strip()}")
            grants[match.group(1)] = match.group(2)
        return grants
    return None


def top_level_permissions(lines):
    return permissions(lines, 0, len(lines), 0) or {}


def check(workflows_dir=WORKFLOWS):
    files = {path.name: path.read_text().splitlines() for path in
             (*workflows_dir.glob("*.yml"), *workflows_dir.glob("*.yaml"))}
    errors = []
    for caller_name, lines in files.items():
        caller_grants = top_level_permissions(lines)
        current_job = None
        job_start = 0
        for index, line in enumerate(lines):
            job_match = JOB.fullmatch(line)
            if job_match:
                current_job, job_start = job_match.group(1), index
            call_match = CALL.fullmatch(line)
            if not call_match:
                continue
            callee_name = call_match.group(1)
            if current_job is None or callee_name not in files:
                errors.append(f"{caller_name}:{index + 1}: unresolved reusable workflow call")
                continue
            job_grants = permissions(lines, job_start, index, 4)
            available = caller_grants if job_grants is None else job_grants
            required = top_level_permissions(files[callee_name])
            for scope, level in required.items():
                allowed = available.get(scope, "none")
                if PERMISSION_LEVEL[allowed] < PERMISSION_LEVEL[level]:
                    errors.append(
                        f"{caller_name}:{index + 1}: job {current_job} calls {callee_name} "
                        f"with {scope}: {allowed}; called workflow requests {level}"
                    )
    return errors


if __name__ == "__main__":
    problems = check()
    if problems:
        print("\n".join(problems), file=sys.stderr)
        raise SystemExit(1)
    print("Reusable workflow permissions are compatible")
