import importlib.util
import unittest
from pathlib import Path
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
