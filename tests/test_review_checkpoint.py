import importlib.util
from pathlib import Path
from datetime import datetime, timezone, timedelta
import unittest

spec = importlib.util.spec_from_file_location('review_checkpoint', Path(__file__).resolve().parents[1] / 'scripts/review_checkpoint.py')
checkpoint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checkpoint)

class ReviewCheckpointTests(unittest.TestCase):
    def snapshot(self):
        return {'as_of':datetime.now(timezone.utc).isoformat(), 'tables':{t:[] for t in checkpoint.TABLES}}

    def test_expired_and_incomplete_snapshots_fail_closed(self):
        s=self.snapshot(); s['as_of']=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
        with self.assertRaises(ValueError): checkpoint.SnapshotStore(s)
        s=self.snapshot(); del s['tables']['sampled_videos']
        with self.assertRaises(ValueError): checkpoint.SnapshotStore(s)

    def test_unknown_review_cannot_create_an_outbox(self):
        s=checkpoint.SnapshotStore(self.snapshot())
        with self.assertRaises(ValueError): checkpoint.import_reviews(s,[{'queue_record_id':'forged'}])
        self.assertEqual(s.outbox,[])

    def test_independent_comment_review_survives_reclassification_retry(self):
        from test_hybrid import HybridTests, label
        from eiim.hybrid import VERSION, reclassify, latest_labels, labels
        from eiim.storage import record
        from eiim.calibration import current_reviews
        from unittest.mock import Mock
        s=HybridTests().make_transcript_store()
        s.batch({'id':'2026-W40'}, 'test')
        value=label()
        row=record('pipeline_runs','2026-W40','coded',{'hybrid_version':VERSION,'label':value,'classified_at':'2026-10-04T00:00:00Z'},'v')
        s.write('2026-W40',[row])
        c=value['comments'][0]
        fields=['response_focus','alignment','stance_target','sentiment','sentiment_target']
        item={'version':VERSION,'item_type':'hybrid_comment','queue_record_id':'coded','queue_hash':row['record']['payload_hash'],'comment_id':c['comment_id'],'reviewer':'Human','reviewed_at':'2026-10-07T10:00:00Z','basis':'english_transcript','human_label':{k:c[k] for k in fields},'decisions':{k:'agree' for k in fields}}
        checkpoint.import_reviews(s,[item])
        classifier=Mock(); classifier.cfg={}
        reclassify(s,'2026-W40',classifier)
        classifier.request.assert_not_called()
        self.assertEqual(latest_labels(labels(s))[0]['id'],'coded')
        self.assertIn(('coded',c['comment_id']),current_reviews(s))
