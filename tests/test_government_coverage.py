import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import collect_government_news as collector
import government_coverage as coverage
from verify_government_source_coverage import verify


class GovernmentCoverageTests(unittest.TestCase):
    def setUp(self):
        self.end=dt.datetime.fromisoformat('2026-11-26T14:00:00+00:00')
        self.zones={'US':ZoneInfo('America/New_York'),'CA':ZoneInfo('America/Toronto')}

    def test_missing_daily_proof_reconciles_history_in_source_timezone(self):
        start,full=coverage.discovery_window({'source_cursors':{'CA':self.end.isoformat()}},'CA',self.end,self.zones)
        self.assertEqual(start.isoformat(),'2026-10-01T04:00:00+00:00')
        self.assertTrue(full)
        self.assertEqual(coverage.discovery_window({},'US',self.end,self.zones)[0].isoformat(),
                         '2026-10-04T04:00:00+00:00')

    def test_next_day_rescans_history_and_same_day_revisits_backdated_posts(self):
        state={'source_cursors':{'US':self.end.isoformat()},'source_reconciliations':{
            'US':{'policy':coverage.POLICY,'day':'2026-11-26'}}}
        start,full=coverage.discovery_window(state,'US',self.end,self.zones)
        self.assertEqual(start,self.end-dt.timedelta(days=14));self.assertFalse(full)
        self.assertTrue(coverage.discovery_window(state,'US',self.end+dt.timedelta(days=1),self.zones)[1])

    def test_changed_policy_cannot_reuse_old_complete_proof(self):
        state={'source_reconciliations':{'US':{'policy':'old-narrow-scope','day':'2026-11-26'}}}
        self.assertTrue(coverage.discovery_window(state,'US',self.end,self.zones)[1])

    def test_explicit_calendar_start_uses_each_publishers_local_midnight(self):
        zones={'CN':ZoneInfo('Asia/Shanghai'),'CA':self.zones['CA']}
        for code in zones:
            start,full=coverage.discovery_window({},code,self.end,zones,dt.date(2026,10,1))
            self.assertEqual(start.astimezone(zones[code]).isoformat()[:19],'2026-10-01T00:00:00')
            self.assertTrue(full)

    def test_omitted_active_source_cannot_be_reported_as_complete_coverage(self):
        item,proof=self.proof();proof['active_country_codes'].append('CA')
        with self.assertRaisesRegex(ValueError,'omits'):
            verify(proof,{'as_of':self.end.isoformat(),'items':[item]})

    def test_cms_slug_change_keeps_existing_id_and_human_correction(self):
        old={'id':'preserve-this-id','country_code':'KZ','url':'https://primeminister.kz/kz/news/old-title-32004',
             'human_reviewed':True,'english_summary':'Owner approved copy.'}
        entry={'country_code':'KZ','url':'https://primeminister.kz/kz/news/digital_office/new-title-32004'}
        found=coverage.match_record(entry,coverage.index_records([old]));self.assertIs(found,old)
        coverage.register_aliases(found,entry)
        self.assertEqual(old['id'],'preserve-this-id');self.assertEqual(old['english_summary'],'Owner approved copy.')
        self.assertEqual(old['source_aliases'],[entry['url']])

    def test_tracking_query_order_and_fragment_are_not_new_announcements(self):
        a='https://www.gov.sm/pub1/news?idItem=17128c60-f60c-4702-8bbf-e527ebb0be60&utm_source=x'
        b='https://www.gov.sm/pub1/renamed?idItem=17128c60-f60c-4702-8bbf-e527ebb0be60#detail'
        self.assertEqual(coverage.publisher_identity('SM',a),coverage.publisher_identity('SM',b))
        self.assertEqual(coverage.publisher_identity('AD','https://gov.example/a?b=2&a=1&utm_source=x#part'),
                         coverage.publisher_identity('AD','https://gov.example/a?a=1&b=2'))

    def test_malta_language_pair_preserves_an_existing_reviewed_release(self):
        old={'id':'keep-maltese-id','country_code':'MT','human_reviewed':True,
             'url':'https://departmentofinformation.gov.mt/press-release/2026/pr261927'}
        entry={'country_code':'MT','url':'https://departmentofinformation.gov.mt/press-release/2026/pr261927-0'}
        self.assertIs(coverage.match_record(entry,coverage.index_records([old])),old)

    def test_different_documents_or_countries_cannot_merge_by_title_or_time(self):
        first={'id':'one','country_code':'CA','url':'https://www.canada.ca/en/a/news/2026/11/one.html'}
        other={'country_code':'CA','url':'https://www.canada.ca/en/a/news/2026/11/two.html'}
        self.assertIsNone(coverage.match_record(other,coverage.index_records([first])))

    def proof(self):
        item={'id':'one','country_code':'US','url':'https://www.whitehouse.gov/releases/2026/11/ai/'}
        row=coverage.coverage_row({'iso2':'US','name':'United States','url':'https://www.whitehouse.gov/news/'},
            [item],coverage.index_records([item]),full=True,start=self.end-dt.timedelta(days=30),end=self.end)
        return item,{'active_country_codes':['US'],'disabled_country_codes':['FR'],'sources':[row]}

    def test_exact_archive_identity_is_required_in_live_records(self):
        item,proof=self.proof();result=verify(proof,{'as_of':self.end.isoformat(),'items':[item]})
        self.assertTrue(result['complete']);self.assertEqual(result['archive_records_checked'],1)
        with self.assertRaisesRegex(ValueError,'absent'):
            verify(proof,{'as_of':self.end.isoformat(),'items':[]})

    def test_live_copy_and_labels_must_match_the_saved_publication(self):
        item,proof=self.proof();snapshot={'as_of':self.end.isoformat(),'items':[{**item,'english_summary':'Correct source-bound copy.'}]}
        self.assertTrue(verify(proof,snapshot,snapshot)['saved_publication_fields_match'])
        with self.assertRaisesRegex(ValueError,'english_summary'):
            verify(proof,{'as_of':snapshot['as_of'],'items':[{**item,'english_summary':'Stale copy.'}]},snapshot)
        with self.assertRaisesRegex(ValueError,'cutoff'):
            verify(proof,{**snapshot,'as_of':'2026-11-25T14:00:00+00:00'},snapshot)

    def test_inaccessible_source_is_partial_not_zero_announcements(self):
        item,proof=self.proof();proof['sources'][0].update(status='source_unverified',error='Timeout')
        result=verify(proof,{'as_of':self.end.isoformat(),'items':[item]})
        self.assertFalse(result['complete']);self.assertEqual(result['verified_country_count'],0)

    def test_false_zero_with_saved_records_cannot_advance_or_pass_verification(self):
        item,proof=self.proof();item['published_at']=self.end.isoformat()
        with self.assertRaisesRegex(RuntimeError,'zero despite saved'):
            coverage.validate_archive_window({'iso2':'US'},[],[item],self.end-dt.timedelta(days=30),self.end,True)
        proof['sources'][0].update(archive_unique_records=0,archive_records=[])
        result=verify(proof,{'as_of':self.end.isoformat(),'items':[item]})
        self.assertFalse(result['complete']);self.assertEqual(result['verified_country_count'],0)

    def test_duplicate_publisher_identity_fails_even_with_different_record_ids(self):
        item,proof=self.proof()
        with self.assertRaisesRegex(ValueError,'Duplicate publisher'):
            verify(proof,{'as_of':self.end.isoformat(),'items':[item,{**item,'id':'two'}]})

    def test_separate_translation_record_cannot_duplicate_a_publisher_language_pair(self):
        item,proof=self.proof()
        alternate='https://www.whitehouse.gov/releases/2026/11/translated/'
        with self.assertRaisesRegex(ValueError,'Duplicate publisher'):
            verify(proof,{'as_of':self.end.isoformat(),'items':[{**item,'source_aliases':[alternate]},
                {**item,'id':'translated','url':alternate}]})

    def test_atomic_checkpoint_saves_preserve_daily_and_private_progress(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'state.json';state={'last_successful_collection_end':None,
                'source_reconciliations':{'CA':{'policy':coverage.POLICY}},'source_metadata':{'CA':{'a':'proof'}}}
            with patch.object(collector,'STATE',target):
                collector.save_government_checkpoint(state,[{'id':'private','translation_checkpoint':{'chunk':'done'}}],{},True)
            saved=json.loads(target.read_text());self.assertEqual(saved['source_metadata'],state['source_metadata'])
            self.assertEqual(saved['source_reconciliations'],state['source_reconciliations'])
            self.assertEqual(saved['items'][0]['translation_checkpoint'],{'chunk':'done'})


if __name__=='__main__':unittest.main()
