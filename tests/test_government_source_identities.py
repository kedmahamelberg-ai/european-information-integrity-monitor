import datetime as dt
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import collect_government_news as collector
from government_source_identities import REGISTRY
from government_coverage import publisher_identity, reconcile_coverage_ids
from verify_government_source_coverage import verify


class PublisherIdentityTests(unittest.TestCase):
    def setUp(self):
        self.rows = json.loads(REGISTRY.read_text())['identities']

    def test_every_verified_rename_keeps_the_original_record_id(self):
        for row in self.rows:
            with self.subTest(id=row['id']):
                for url in [row['preferred_url'], *row['aliases']]:
                    self.assertEqual(collector.source_record_id(url), row['id'])
                    self.assertEqual(collector.source_record_id(url+'/'), row['id'])
                    self.assertEqual(publisher_identity('IS', url), publisher_identity('IS', row['preferred_url']))

    def test_merge_preserves_owner_copy_and_source_binding_in_either_order(self):
        row = self.rows[0]
        approved = {'id':row['id'], 'country_code':'IS', 'url':row['preferred_url'],
            'human_reviewed':True, 'classification_status':'provisional',
            'english_summary':'Owner approved wording.', 'source_text_sha256':'approved-hash'}
        duplicate = {'id':'duplicate', 'country_code':'IS', 'url':row['aliases'][0],
            'classification_status':'provisional', 'english_summary':'A new model answer.'}
        for order in ([approved, duplicate], [duplicate, approved]):
            merged = list(collector.canonical_government_items(order).values())
            self.assertEqual(len(merged), 1)
            for key, value in approved.items():
                self.assertEqual(merged[0][key], value)
            self.assertEqual(merged[0]['source_aliases'], row['aliases'])

    def test_unverified_date_and_title_similarities_remain_distinct(self):
        base='https://www.stjornarradid.is/efst-a-baugi/frettir/stok-frett/'
        rows=[{'url':base+'2026-11-19', 'title':'Same title'},
              {'url':base+'2026-11-19-different-article', 'title':'Same title'}]
        self.assertEqual(len(collector.canonical_government_items(rows)), 2)

    def test_alias_merge_rebinds_archive_proof_and_verifier_detects_reintroduced_duplicate(self):
        row=self.rows[0]
        old={'id':row['id'], 'country_code':'IS', 'url':row['preferred_url']}
        record={'url':row['aliases'][0], 'id':'new-alias-id'}
        report={'active_country_codes':['IS'], 'sources':[{'country_code':'IS', 'status':'complete',
            'source_url':'https://www.stjornarradid.is/efst-a-baugi/frettir/',
            'archive_unique_records':1, 'archive_records':[record]}]}
        reconcile_coverage_ids(report, [old])
        self.assertEqual(record['id'], old['id'])
        snapshot={'as_of':'2026-11-26T18:00:00Z', 'items':[old]}
        self.assertTrue(verify(report, snapshot)['complete'])
        snapshot['items'].append({**old,'id':'new-alias-id','url':row['aliases'][0]})
        with self.assertRaisesRegex(ValueError, 'Duplicate publisher'):
            verify(report, snapshot)


if __name__=='__main__':
    unittest.main()
