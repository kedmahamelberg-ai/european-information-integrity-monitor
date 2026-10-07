import importlib.util
from datetime import datetime, timezone, timedelta
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('local_recovery', Path(__file__).resolve().parents[1] / 'scripts/local_recovery.py')
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)

class LocalRecoveryTests(unittest.TestCase):
    def test_saved_expired_and_invalid_sources_never_enter_queue(self):
        now = datetime(2026,10,7,tzinfo=timezone.utc)
        source={'id':'abcdefghijk','batch':'2026-W40','caption_state':'unverified'}
        self.assertEqual(recovery.candidates([source],[],now),[source])
        for changes in ({'caption_state':'saved'},{'batch':'2026-W01'},{'id':'bad'}):
            self.assertEqual(recovery.candidates([{**source,**changes}],[],now),[])
        record={'record':{'batch_id':source['batch'],'video_id':source['id'],'payload':{'transcript_english':[{'text':'saved'}]}}}
        self.assertEqual(recovery.candidates([source],[record],now),[])

    def test_cooldowns_and_untouched_first(self):
        now = datetime(2026,10,7,tzinfo=timezone.utc)
        old={'id':'abcdefghijk','batch':'2026-W40'}; fresh={**old,'id':'12345678901'}
        def row(days,reason):
            return {'record':{'batch_id':old['batch'],'video_id':old['id'],'payload':{
                'audio_attempted_at':(now-timedelta(days=days)).isoformat(),'failure_reason':reason}}}
        self.assertEqual(recovery.candidates([old,fresh],[row(.5,'AudioAccessUnavailable')],now),[fresh])
        self.assertEqual(recovery.candidates([old,fresh],[row(2,'AudioAccessUnavailable')],now),[fresh,old])
        self.assertEqual(recovery.candidates([old],[row(2,'AudioNoUsableSpeech')],now),[])

class ContinuationTests(unittest.TestCase):
    def run_queue(self, size, *, seconds_per_video=1, budget=14400, blocked=False):
        clock = [0]
        readers, written, states = [], [], []
        class Reader:
            def __init__(self, max_videos, max_seconds):
                self.limit, self.seconds = max_videos, max_seconds
                self.started = clock[0]
                self.attempted = 0
                self.stopped = None
                readers.append(self)
            def check(self, source):
                if self.attempted >= self.limit or clock[0]-self.started >= self.seconds:
                    self.stopped = 'audio_run_limit'
                    return None
                self.attempted += 1
                clock[0] += seconds_per_video
                if blocked:
                    self.stopped = 'audio_access_unavailable'
                    return {'failure_reason':'AudioAccessBlocked'}
                return {'transcript_english':[{'text':'private evidence'}]}
        result = recovery.recover_queue(
            [{'id':str(i), 'batch':'2026-W40'} for i in range(size)],
            lambda source, result: written.append(source['id']), states.append,
            reader_factory=Reader, clock=lambda:clock[0], max_seconds=budget)
        return result, readers, written, states

    def test_157_sources_continue_across_80_source_boundary_without_duplicates(self):
        final, readers, written, states = self.run_queue(157)
        self.assertEqual([r.attempted for r in readers], [80,77])
        self.assertEqual(len(set(written)),157)
        self.assertEqual(final['stop_reason'],'eligible_queue_complete')
        self.assertEqual(final['remaining_eligible'],0)
        self.assertNotIn('private evidence',str(states))

    def test_45_minute_chunk_continues_automatically(self):
        final, readers, written, _ = self.run_queue(100, seconds_per_video=60)
        self.assertEqual([r.attempted for r in readers],[45,45,10])
        self.assertEqual(len(written),100)
        self.assertEqual(final['status'],'complete')

    def test_session_limit_preserves_remaining_work_for_next_checkpoint(self):
        final, readers, written, _ = self.run_queue(100, seconds_per_video=60,budget=300)
        self.assertEqual(len(written),5)
        self.assertEqual(final['remaining_eligible'],95)
        self.assertEqual(final['stop_reason'],'session_time_limit')

    def test_access_block_is_not_retried_as_normal_chunk_boundary(self):
        final, readers, written, _ = self.run_queue(100, blocked=True)
        self.assertEqual(len(readers),1)
        self.assertEqual(len(written),1)
        self.assertEqual(final['remaining_eligible'],99)
        self.assertEqual(final['stop_reason'],'audio_access_unavailable')
