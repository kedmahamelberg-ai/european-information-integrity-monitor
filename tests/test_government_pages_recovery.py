import copy
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from recover_government_pages import validate_archive, validate_source


class GovernmentPagesRecovery(unittest.TestCase):
    def setUp(self):
        self.repository = 'owner/monitor'
        self.run = {'id': 123, 'head_sha': 'checked-commit', 'head_branch': 'main',
                    'repository': {'full_name': self.repository},
                    'head_repository': {'full_name': self.repository},
                    'path': '.github/workflows/government-news.yml',
                    'status': 'completed', 'conclusion': 'failure'}
        self.jobs = [{'name': 'collect', 'status': 'completed', 'conclusion': 'failure', 'steps': [
            {'name': name, 'conclusion': 'success'} for name in (
                'Collect, translate and classify official government news',
                'Save collection checkpoint', 'Build public dashboard')]}]
        self.jobs[0]['steps'].append({'name': 'Deploy updated monitor', 'conclusion': 'failure'})
        self.artifacts = [{'id': 456, 'name': 'github-pages', 'expired': False,
                           'workflow_run': {'id': 123, 'head_sha': 'checked-commit'}}]

    def test_legacy_deploy_failure_reuses_the_saved_build(self):
        self.assertEqual(validate_source(self.run, self.jobs, self.artifacts, self.repository), 456)

    def test_collection_failure_cannot_be_recovered_as_a_publication(self):
        self.jobs[0]['steps'][0]['conclusion'] = 'failure'
        with self.assertRaisesRegex(ValueError, 'Collection or build failed'):
            validate_source(self.run, self.jobs, self.artifacts, self.repository)

    def test_fork_and_wrong_artifact_provenance_are_rejected(self):
        fork = copy.deepcopy(self.run); fork['head_repository']['full_name'] = 'outside/fork'
        with self.assertRaisesRegex(ValueError, 'this repository main'):
            validate_source(fork, self.jobs, self.artifacts, self.repository)
        self.artifacts[0]['workflow_run']['head_sha'] = 'other-commit'
        with self.assertRaisesRegex(ValueError, 'provenance'):
            validate_source(self.run, self.jobs, self.artifacts, self.repository)

    def test_isolated_deploy_can_recover_without_repeating_successful_collection(self):
        self.jobs = [{'name': 'collect', 'status': 'completed', 'conclusion': 'success'},
                     {'name': 'deploy', 'status': 'completed', 'conclusion': 'failure'}]
        self.assertEqual(validate_source(self.run, self.jobs, self.artifacts, self.repository), 456)

    def archive(self, path, extra=None, duplicate=False):
        with tarfile.open(path, 'w') as archive:
            files = {'./index.html': b'<html>Saved build</html>',
                     './government-data.json': json.dumps({'as_of': '2026-11-25T14:00:00Z',
                         'items': [{'id': 'one'}, {'id': 'one' if duplicate else 'two'}]}).encode(),
                     './data.json': b'{"videos":[]}'}
            for name, payload in files.items():
                info = tarfile.TarInfo(name); info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
            if extra:
                archive.addfile(extra)

    def test_archive_validates_public_files_without_extracting_source_or_reclassifying(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'artifact.tar'; self.archive(path)
            result = validate_archive(path)
            self.assertEqual(result['government_items'], 2)
            self.assertEqual(len(list(Path(directory).iterdir())), 1)
            self.archive(path, duplicate=True)
            with self.assertRaisesRegex(ValueError, 'duplicate IDs'):
                validate_archive(path)

    def test_unsafe_paths_and_links_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'artifact.tar'
            for name in ('../secret', '/absolute'):
                self.archive(path, tarfile.TarInfo(name))
                with self.assertRaisesRegex(ValueError, 'Unsafe path'):
                    validate_archive(path)
            link = tarfile.TarInfo('link'); link.type = tarfile.SYMTYPE; link.linkname = '../secret'
            self.archive(path, link)
            with self.assertRaisesRegex(ValueError, 'Links and special files'):
                validate_archive(path)

    def test_deployment_retry_has_no_collection_or_model_step(self):
        workflow = (ROOT / '.github/workflows/government-news.yml').read_text()
        deploy = workflow.split('\n  deploy:\n', 1)[1]
        self.assertIn('needs: collect', deploy)
        self.assertNotIn('collect_government_news.py', deploy)
        self.assertNotIn('OPENAI_API_KEY', deploy)
        recovery = (ROOT / '.github/workflows/recover-government-pages.yml').read_text()
        self.assertNotIn('collect_government_news.py', recovery)
        self.assertNotIn('OPENAI_API_KEY', recovery)
        self.assertIn('actions/download-artifact@v4', recovery)
        self.assertIn('[saved-pages-recovery]', (ROOT / '.github/workflows/site.yml').read_text())
        action = (ROOT / '.github/actions/deploy-monitor-pages/action.yml').read_text()
        self.assertEqual(action.count('uses: actions/deploy-pages@v4'), 2)
        self.assertIn("if: steps.deployment.outcome == 'failure'", action)


if __name__ == '__main__':
    unittest.main()
