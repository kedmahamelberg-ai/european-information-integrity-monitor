"""Catch shell syntax errors in the scheduled retention step before release."""

import re
import subprocess
import textwrap
import unittest
from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/retention.yml"


class RetentionWorkflowTests(unittest.TestCase):
    def test_inline_shell_blocks_parse(self):
        lines = WORKFLOW.read_text().splitlines()
        scripts = []
        for index, line in enumerate(lines):
            match = re.match(r"^( *)run: \|\s*$", line)
            if not match:
                continue
            indent = len(match.group(1))
            body = []
            for part in lines[index + 1 :]:
                if part.strip() and len(part) - len(part.lstrip(" ")) <= indent:
                    break
                body.append(part)
            scripts.append(textwrap.dedent("\n".join(body)) + "\n")
        self.assertTrue(scripts, "Retention workflow has no shell script to check")
        for script in scripts:
            with self.subTest(script=script.splitlines()[0]):
                check = subprocess.run(
                    ["bash", "-n"], input=script, text=True, capture_output=True,
                    check=False,
                )
                self.assertEqual(check.returncode, 0, check.stderr)
