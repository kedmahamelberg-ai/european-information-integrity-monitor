import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from eiim.hybrid_public import export_public, comment_summary, _audit_progress
from eiim.hybrid import VERSION
from eiim.review_sampling import sample_plan
from eiim.storage import record
from eiim.language_access import POLICY_VERSION
import test_hybrid as fixtures


class PublicCoverageTests(unittest.TestCase):
    def test_internal_viewpoints_are_not_exported_publicly(self):
        s = fixtures.HybridTests().make_transcript_store()
        s.batch({'id': '2026-W40'}, 'test')
        payload = {
            'hybrid_version': VERSION,
            'video_id': 'v',
            'label': fixtures.label(),
            'classified_at': '2026-10-04T00:00:00Z',
            'model_version': 'test',
            'transcript_truncated': False,
        }
        s.write('2026-W40', [
            record('pipeline_runs', '2026-W40', 'hybrid', payload, 'v')
        ])
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'public.json'
            export_public(s, p)
            out = json.loads(p.read_text())
        coded = next(video for video in out['videos'] if video.get('label'))
        self.assertNotIn('viewpoint_structure', coded['label'])
        self.assertNotIn('viewpoints', coded['label'])
        self.assertNotIn('viewpoint_ids', json.dumps(out))

    def test_blocked_source_visible_without_inventing_content_labels(self):
        s = fixtures.HybridTests().make_transcript_store()
        s.batch({'id': '2026-W40'}, 'test')
        s.write('2026-W40', [
            record('candidate_videos', '2026-W40', 'blocked-candidate', {'title': 'Public source', 'countries': ['FR'], 'published_at': '2026-10-04T12:00:00Z'}, 'blocked'),
            record('sampled_videos', '2026-W40', 'blocked-sample', {'selected_for_sample': True}, 'blocked'),
            record('pipeline_runs', '2026-W40', 'blocked-access', {'english_access_video_id': 'blocked', 'policy_version': POLICY_VERSION, 'eligible': False, 'original_language': 'fr', 'status': 'english_access_unverified', 'failure_reason': 'IpBlocked', 'checked_at': '2026-10-05T00:00:00Z', 'transcript_english': []}, 'blocked'),
        ])
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'public.json'; export_public(s,p); out=json.loads(p.read_text())
        self.assertEqual(out['collection']['sampled_videos'], 2)
        self.assertEqual(out['caption_health'], {'saved': 1, 'blocked': 1})
        blocked=next(x for x in out['inventory'] if x['id']=='blocked')
        self.assertEqual(blocked['caption_state'], 'blocked')
        self.assertEqual(blocked['published_at'], '2026-10-04T12:00:00Z')
        self.assertNotIn('label',blocked)
        self.assertNotIn('blocked', [x['id'] for x in out['videos']])
        self.assertNotIn('transcript_english', json.dumps(out))

    def test_human_comment_correction_overrides_ai_in_aggregate(self):
        row={'id':'r','payload':{'label':fixtures.label()}}
        review={'human_label':dict(fixtures.label()['comments'][0], alignment='opposes')}
        out=comment_summary(row,{('r','c'):review})
        self.assertEqual(out['alignment'], {'opposes':1})
        self.assertEqual(out['sentiment'], {'negative':1})
        self.assertEqual(out['human_reviewed'],1)
        self.assertEqual(out['ai_only'],0)
        self.assertNotIn('rationale', json.dumps(out))
        self.assertNotIn('stance_target', json.dumps(out))

    def test_public_audit_uses_same_comment_stratified_video_plan_as_review(self):
        s = fixtures.HybridTests().make_transcript_store()
        s.batch({'id': '2026-W40'}, 'test')
        with tempfile.TemporaryDirectory() as d, patch(
            'eiim.hybrid_public.sample_plan', wraps=sample_plan
        ) as planner:
            export_public(s, Path(d) / 'public.json')
        self.assertIn('comments_by_video', planner.call_args.kwargs)
        self.assertEqual(planner.call_args.kwargs['comments_by_video'], {})

    def test_audit_progress_retains_legacy_reviews_and_future_assignments(self):
        rows = {'v1': {'id': 'r1'}, 'v2': {'id': 'r2'}}
        plan = {'target': 30, 'selected_video_ids': ['other']}
        self.assertEqual(_audit_progress(plan, rows, {'r1': {}, 'r2': {}}), (30, 2))
        assigned = {
            'r1': {'review_assignment': {'selected': True, 'target': 6}},
            'r2': {'review_assignment': {'selected': True, 'target': 6}},
        }
        self.assertEqual(_audit_progress(plan, rows, assigned), (6, 2))
