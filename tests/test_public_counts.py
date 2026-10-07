import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('counts',Path(__file__).resolve().parents[1]/'scripts/check_public_counts.py')
counts=importlib.util.module_from_spec(spec)
spec.loader.exec_module(counts)

def snapshot():
    return {'mode':'live','inventory':[{'id':'v','batch':'week'}],
      'caption_health':{'saved':1},
      'collection':{'sampled_videos':1,'transcript_eligible':1,'classified_videos':1,
                    'awaiting_transcript':0,'classified_comments':1,'retained_comments':2,'reviewed_comments':0},
      'videos':[{'id':'v','batch':'week','label':{'relevance':'related'},
                 'classified_comments':1,'retained_comments':2,
                 'responses':{'total':1,'human_reviewed':0,'alignment':{'supports':1},
                              'sentiment':{'neutral':1},'alignment_sentiment':{'supports':{'neutral':1}}}}]}

class PublicCountsTests(unittest.TestCase):
    def test_partial_classification_is_valid_without_fabricating_missing_comments(self):
        counts.check(snapshot())
    def test_disagreeing_category_and_joint_counts_block_publication(self):
        for field in ['alignment','sentiment','alignment_sentiment']:
            d=snapshot(); d['videos'][0]['responses'][field]={}
            with self.assertRaises(ValueError):counts.check(d)
    def test_duplicate_video_or_wrong_global_count_blocks_publication(self):
        d=snapshot();d['videos']*=2
        with self.assertRaises(ValueError):counts.check(d)
        d=snapshot();d['collection']['classified_videos']=2
        with self.assertRaises(ValueError):counts.check(d)
