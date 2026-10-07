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
    def test_auth_errors_and_writes_are_not_retried(self, sleep):
        for name, status in [('eiim_read',401), ('eiim_read',403), ('eiim_write',500)]:
            with patch('eiim.storage.urllib.request.urlopen', side_effect=self.http(status)) as request:
                with self.assertRaises(RuntimeError):
                    self.client().rpc(name, {})
                self.assertEqual(request.call_count, 1)
        sleep.assert_not_called()

    @patch('eiim.storage.time.sleep')
    def test_network_read_failure_recovers(self, sleep):
        with patch('eiim.storage.urllib.request.urlopen', side_effect=[
            urllib.error.URLError('private network detail'), io.BytesIO(b'[]')
        ]):
            self.assertEqual(self.client().read('pipeline_runs'), [])

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
