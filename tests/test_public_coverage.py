import json
import tempfile
import unittest
from pathlib import Path
from eiim.hybrid_public import export_public, comment_summary
from eiim.storage import record
from eiim.language_access import POLICY_VERSION
import test_hybrid as fixtures


class PublicCoverageTests(unittest.TestCase):
    def test_blocked_source_visible_without_inventing_content_labels(self):
        s = fixtures.HybridTests().make_transcript_store()
        s.batch({'id': '2026-W40'}, 'test')
        s.write('2026-W40', [
            record('candidate_videos', '2026-W40', 'blocked-candidate', {'title': 'Public source', 'countries': ['FR']}, 'blocked'),
            record('sampled_videos', '2026-W40', 'blocked-sample', {'selected_for_sample': True}, 'blocked'),
            record('pipeline_runs', '2026-W40', 'blocked-access', {'english_access_video_id': 'blocked', 'policy_version': POLICY_VERSION, 'eligible': False, 'original_language': 'fr', 'status': 'english_access_unverified', 'failure_reason': 'IpBlocked', 'checked_at': '2026-10-05T00:00:00Z', 'transcript_english': []}, 'blocked'),
        ])
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'public.json'; export_public(s,p); out=json.loads(p.read_text())
        self.assertEqual(out['collection']['sampled_videos'], 2)
        self.assertEqual(out['caption_health'], {'saved': 1, 'blocked': 1})
        blocked=next(x for x in out['inventory'] if x['id']=='blocked')
        self.assertEqual(blocked['caption_state'], 'blocked')
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
