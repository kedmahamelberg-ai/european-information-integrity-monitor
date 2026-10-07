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
