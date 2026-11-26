import datetime as dt
from pathlib import Path
import sys
import subprocess
import unittest
import io
import json
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from continue_government_backlog import plan,pending_work,GOVERNMENT,preflight


class GovernmentBacklogTests(unittest.TestCase):
    def setUp(self):
        self.now=dt.datetime.fromisoformat('2026-11-26T17:00:00+00:00')
        self.run={'id':123,'status':'completed','conclusion':'success','path':GOVERNMENT,'head_branch':'main'}

    def test_only_successful_main_run_can_continue(self):
        self.assertTrue(plan(self.now,[self.run],[])['enabled'])
        for changes in ({'conclusion':'failure'},{'head_branch':'candidate'},{'status':'in_progress'}):
            with self.subTest(changes=changes):self.assertFalse(plan(self.now,[{**self.run,**changes}],[])['enabled'])

    def test_newer_failed_run_prevents_retrying_older_success(self):
        self.assertFalse(plan(self.now,[self.run,{**self.run,'id':124,'conclusion':'failure'}],[])['enabled'])

    def test_active_collection_audit_or_publication_blocks_dispatch(self):
        for path in ('government-news.yml','government-source-audit.yml','site.yml','retention.yml','recover-government-pages.yml'):
            with self.subTest(path=path):
                self.assertFalse(plan(self.now,[self.run,{'id':124,'status':'queued','path':'.github/workflows/'+path}],[])['enabled'])
        self.assertFalse(plan(self.now,[self.run],[{'status':'in_progress','name':'Update Brief Government AI Announcements'}])['enabled'])

    def test_amsterdam_summer_and_winter_collection_windows_stay_clear(self):
        for date in ('2026-11-26T06:30:00+00:00','2026-11-26T12:30:00+00:00',
                     '2027-07-01T05:30:00+00:00','2027-07-01T11:30:00+00:00',
                     '2026-11-26T08:00:00+00:00','2026-11-26T08:05:00+00:00'):
            with self.subTest(date=date):self.assertFalse(plan(dt.datetime.fromisoformat(date),[self.run],[])['enabled'])

    def state(self):
        return {'calibration_complete':True,'classification_progress':{'run_id':'123','classified':1},
                'items':[{'classification_status':'pending_classification'}]}

    def test_only_fresh_pending_work_is_dispatched(self):
        state=self.state();state['items'].extend([
            {'classification_status':'needs_review'},
            {'classification_status':'pending_classification','classification_error':'rate_limit_exceeded'},
            {'classification_status':'pending_classification','human_reviewed':True},
            {'classification_status':'pending_classification','source_reviewed':True}])
        self.assertEqual(pending_work(state,123)[0],1)

    def test_exact_checkpoint_progress_and_calibration_are_required(self):
        for key,value in [('run_id','122'),('classified',0)]:
            state=self.state();state['classification_progress'][key]=value
            self.assertEqual(pending_work(state,123)[0],0)
        state=self.state();state['calibration_complete']=False
        self.assertEqual(pending_work(state,123)[0],0)

    def test_drained_queue_stops_without_another_job(self):
        state=self.state();state['items']=[]
        self.assertEqual(pending_work(state,123)[0],0)

    def test_both_repository_checks_use_authentication_before_any_dispatch(self):
        class Response(io.BytesIO):
            status=200
        requests=[]
        def opened(request,timeout):
            requests.append(request)
            return Response(json.dumps({'workflow_runs':[self.run] if len(requests)==1 else []}).encode())
        with patch.dict('os.environ',{'GITHUB_TOKEN':'test-token','GITHUB_REPOSITORY':'owner/monitor'}), \
             patch('continue_government_backlog.urllib.request.urlopen',side_effect=opened):
            preflight()
        self.assertEqual(len(requests),2)
        self.assertIn('aieo-brief/actions/runs?per_page=100',requests[1].full_url)
        self.assertTrue(all(r.get_header('Authorization')=='Bearer test-token' for r in requests))
        self.assertTrue(all(r.get_method()=='GET' for r in requests))

    def test_fresh_only_flag_is_recognized_and_requires_classify_only(self):
        command=Path(__file__).resolve().parents[1]/'scripts/collect_government_news.py'
        result=subprocess.run([sys.executable,str(command),'--fresh-pending-only'],capture_output=True,text=True)
        self.assertEqual(result.returncode,2)
        self.assertIn('requires --classify-only',result.stderr)


if __name__=='__main__':unittest.main()
