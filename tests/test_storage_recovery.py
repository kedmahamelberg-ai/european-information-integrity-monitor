import io
import json
import unittest
import urllib.error
from unittest.mock import patch
from eiim.storage import Store, MemoryStore, ReadSnapshot, record


class StorageRecoveryTests(unittest.TestCase):
    def client(self):
        return Store('https://example.supabase.co', 'private-test-key')

    def http(self, status):
        return urllib.error.HTTPError('https://example.supabase.co', status,
                                      'private response', {}, io.BytesIO(b'secret'))

    @patch('eiim.storage.time.sleep')
    def test_read_recovers_from_server_error_without_changing_request(self, sleep):
        with patch('eiim.storage.urllib.request.urlopen', side_effect=[
            self.http(500), self.http(503), io.BytesIO(b'[{"id":"saved"}]')
        ]) as request:
            self.assertEqual(self.client().read('pipeline_runs', 'b'), [{'id':'saved'}])
            self.assertEqual(request.call_count, 3)
            self.assertEqual(sleep.call_count, 2)
            self.assertEqual(json.loads(request.call_args.args[0].data),
                             {'p_table':'pipeline_runs', 'p_batch':'b'})

    @patch('eiim.storage.time.sleep')
    def test_persistent_failure_is_bounded_and_redacted(self, sleep):
        with patch('eiim.storage.urllib.request.urlopen', side_effect=[self.http(500) for _ in range(3)]) as request:
            with self.assertRaises(RuntimeError) as caught:
                self.client().read('pipeline_runs')
            self.assertEqual(request.call_count, 3)
            self.assertNotIn('secret', str(caught.exception))
            self.assertNotIn('private-test-key', str(caught.exception))

    @patch('eiim.storage.time.sleep')
    def test_auth_errors_are_not_retried(self, sleep):
        for name, status in [('eiim_read',401), ('eiim_read',403)]:
            with patch('eiim.storage.urllib.request.urlopen', side_effect=self.http(status)) as request:
                with self.assertRaises(RuntimeError):
                    self.client().rpc(name, {})
                self.assertEqual(request.call_count, 1)
        sleep.assert_not_called()

    @patch('eiim.storage.time.sleep')
    def test_immutable_write_recovers_with_identical_request(self, sleep):
        saved = io.BytesIO(b'{"accepted":1,"stage":null}')
        saved.__enter__ = lambda value: value
        saved.__exit__ = lambda *args: None
        with patch('eiim.storage.urllib.request.urlopen', side_effect=[
            urllib.error.URLError('private network detail'), saved
        ]) as request:
            result = self.client().rpc('eiim_write', {'p_batch':'b','p_stage':None,'p_rows':[]})
            self.assertEqual(result['accepted'], 1)
            self.assertEqual(request.call_count, 2)
            self.assertEqual(request.call_args_list[0].args[0].data,
                             request.call_args_list[1].args[0].data)

    def test_write_chunks_rows_and_sets_stage_only_on_final_chunk(self):
        store = self.client()
        rows = [record('pipeline_runs', 'b', str(i), {'value': i}) for i in range(201)]
        with patch.object(store, 'rpc', side_effect=[
            {'accepted': 200, 'stage': None},
            {'accepted': 1, 'stage': 'discovery_complete'},
        ]) as rpc:
            result = store.write('b', rows, 'discovery_complete')
        self.assertEqual(result, {'accepted': 201, 'stage': 'discovery_complete'})
        self.assertEqual(len(rpc.call_args_list[0].args[1]['p_rows']), 200)
        self.assertIsNone(rpc.call_args_list[0].args[1]['p_stage'])
        self.assertEqual(len(rpc.call_args_list[1].args[1]['p_rows']), 1)
        self.assertEqual(rpc.call_args_list[1].args[1]['p_stage'], 'discovery_complete')

    @patch('eiim.storage.time.sleep')
    def test_network_read_failure_recovers(self, sleep):
        with patch('eiim.storage.urllib.request.urlopen', side_effect=[
            urllib.error.URLError('private network detail'), io.BytesIO(b'[]')
        ]):
            self.assertEqual(self.client().read('pipeline_runs'), [])

    def test_store_caches_reads_and_updates_cached_rows_after_write(self):
        first = [{
            'id': 'old', 'batch_id': 'b', 'video_id': 'v',
            'payload': {'value': 1}, 'payload_hash': 'h1', 'purged_at': None,
        }]
        response = io.BytesIO(json.dumps(first).encode())
        response.__enter__ = lambda value: value
        response.__exit__ = lambda *args: None
        write_response = io.BytesIO(b'{"accepted":1}')
        write_response.__enter__ = lambda value: value
        write_response.__exit__ = lambda *args: None
        store = self.client()
        with patch('eiim.storage.urllib.request.urlopen', side_effect=[response, write_response]) as request:
            rows = store.read('pipeline_runs', 'b')
            rows[0]['payload']['value'] = 99
            self.assertEqual(store.read('pipeline_runs', 'b')[0]['payload']['value'], 1)
            new = record('pipeline_runs', 'b', 'new', {'value': 2}, 'v')
            store.write('b', [new])
            cached = store.read('pipeline_runs', 'b')
            self.assertEqual([r['id'] for r in cached], ['old', 'new'])
            self.assertEqual(request.call_count, 2)

    def test_stage_write_invalidates_cached_batch_status(self):
        batch = [{
            'id': 'b', 'payload': {}, 'config_hash': 'h', 'status': 'started',
            'completed_stages': [],
        }]
        responses = [io.BytesIO(json.dumps(batch).encode()), io.BytesIO(b'{"accepted":0}'),
                     io.BytesIO(json.dumps([{**batch[0], 'status':'published'}]).encode())]
        for response in responses:
            response.__enter__ = lambda value: value
            response.__exit__ = lambda *args: None
        store = self.client()
        with patch('eiim.storage.urllib.request.urlopen', side_effect=responses) as request:
            self.assertEqual(store.read('weekly_batches', 'b')[0]['status'], 'started')
            store.write('b', [], stage='published')
            self.assertEqual(store.read('weekly_batches', 'b')[0]['status'], 'published')
            self.assertEqual(request.call_count, 3)

    def test_snapshot_is_scoped_and_does_not_mutate_stored_reviews(self):
        store = MemoryStore()
        store.write('b', [record('human_validation','b','r',{'reviewer':'Human'})])
        snapshot = ReadSnapshot(store)
        with patch.object(store, 'read', wraps=store.read) as read:
            first = snapshot.read('human_validation','b')
            first[0]['payload']['reviewer'] = 'changed'
            self.assertEqual(snapshot.read('human_validation','b')[0]['payload']['reviewer'], 'Human')
            self.assertEqual(read.call_count, 1)
            store.write('b', [record('human_validation','b','r2',{'reviewer':'New'})])
            self.assertEqual(len(snapshot.read('human_validation','b')), 1)
            self.assertEqual(len(ReadSnapshot(store).read('human_validation','b')), 2)


if __name__ == '__main__':
    unittest.main()
