"""The Pages deploy gate waits for the uploaded artifact, not a fixed delay."""
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from wait_for_pages_artifact import wait_for_artifact


class Response(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self,*_): self.close()


def listing(names):
    return Response(json.dumps({"artifacts":[{"name":name} for name in names]}).encode())


class PagesArtifactTest(unittest.TestCase):
    def test_waits_until_artifact_is_visible(self):
        opener=Mock(side_effect=[listing([]),listing(["github-pages"])])
        sleep=Mock()
        wait_for_artifact("owner/repo","123","test",attempts=3,pause=2,opener=opener,sleep=sleep)
        self.assertEqual(opener.call_count,2)
        sleep.assert_called_once_with(2)
        request=opener.call_args.args[0]
        self.assertEqual(request.full_url,"https://api.github.com/repos/owner/repo/actions/runs/123/artifacts?name=github-pages&per_page=100")

    def test_duplicate_artifacts_fail_explicitly(self):
        with self.assertRaisesRegex(RuntimeError,"Multiple Pages artifacts"):
            wait_for_artifact("owner/repo","123","test",attempts=1,opener=lambda *_args,**_kw: listing(["github-pages","github-pages"]))

    def test_missing_artifact_stops_after_bounded_attempts(self):
        opener=Mock(side_effect=[listing([]),listing([])])
        with self.assertRaisesRegex(RuntimeError,"not visible"):
            wait_for_artifact("owner/repo","123","test",attempts=2,pause=0,opener=opener,sleep=lambda *_:None)
        self.assertEqual(opener.call_count,2)


if __name__=="__main__": unittest.main()
