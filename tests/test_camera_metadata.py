import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('check_cameras',Path(__file__).resolve().parents[1]/'scripts/check_cameras.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class CameraMetadataTests(unittest.TestCase):
    def test_only_current_embeddable_live_broadcasts_qualify(self):
        item={'status':{'embeddable':True},'snippet':{'liveBroadcastContent':'live'},'liveStreamingDetails':{'actualStartTime':'2026-10-05T00:00:00Z'}}
        self.assertEqual(module.camera_status(item),'live')
        item['liveStreamingDetails']['actualEndTime']='2026-10-05T01:00:00Z'
        self.assertEqual(module.camera_status(item),'not_live')
        item['status']['embeddable']=False
        self.assertEqual(module.camera_status(item),'embedding_disabled')
        self.assertEqual(module.camera_status(None),'unavailable')

    def test_strict_refresh_keeps_last_catalogue_when_access_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cameras.json'
            original = {'cameras': [{'id': 'street', 'video_id': 'zMCea32gpmg', 'status': 'live'}]}
            path.write_text(json.dumps(original))
            with patch.object(module.urllib.request, 'urlopen', side_effect=OSError('offline')):
                with self.assertRaisesRegex(RuntimeError, 'keeping the last published directory'):
                    module.refresh(path, 'test-key', strict=True)
            self.assertEqual(json.loads(path.read_text()), original)

    def test_offline_slate_overrides_live_metadata(self):
        self.assertEqual(module.watch_status(
            '{"playabilityStatus":{"status":"LIVE_STREAM_OFFLINE"},"isLiveNow":true}'),
            'not_live')
        self.assertEqual(module.watch_status(
            '{"playabilityStatus":{"status":"OK"},"isLiveNow":true}'), 'live')
        self.assertEqual(module.watch_status(
            '{"playabilityStatus":{"status":"OK"},"isLiveNow":false}'), 'not_live')
