import json
import unittest
from eiim.hybrid_public import comment_summary

class ResponseCrossTabTests(unittest.TestCase):
    def test_joint_counts_apply_human_corrections_without_exposing_comments(self):
        row={"id":"v-label","payload":{"label":{"comments":[
            {"comment_id":"private-one","alignment":"supports","sentiment":"positive","text":"private text"},
            {"comment_id":"private-two","alignment":"supports","sentiment":"negative"}]}}}
        reviews={("v-label","private-one"):{"human_label":{"alignment":"opposes","sentiment":"neutral"}}}
        result=comment_summary(row,reviews)
        self.assertEqual(result['alignment_sentiment'],{'opposes':{'neutral':1},'supports':{'negative':1}})
        self.assertEqual(result['total'],2)
        self.assertEqual(result['human_reviewed'],1)
        self.assertNotIn('private',json.dumps(result))
        self.assertEqual(sum(sum(v.values()) for v in result['alignment_sentiment'].values()),result['total'])
