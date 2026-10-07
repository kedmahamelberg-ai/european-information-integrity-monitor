"""Reject inconsistent public counts before publishing; never inspect private text."""
import json
from pathlib import Path


def check(data):
    if data.get('mode') != 'live':
        return
    videos, inventory, c = data['videos'], data['inventory'], data['collection']
    def require(ok, message):
        if not ok:
            raise ValueError('Public count reconciliation failed: '+message)
    for name, rows in [('videos', videos), ('inventory', inventory)]:
        require(len({(v['batch'],v['id']) for v in rows})==len(rows),name+' duplicates')
    require(c['sampled_videos']==len(inventory),'sample size')
    require(c['transcript_eligible']==len(videos),'English text coverage')
    require(c['classified_videos']==sum(bool(v.get('label')) for v in videos),'classified videos')
    require(c['awaiting_transcript']+c['transcript_eligible']==c['sampled_videos'],'missing text')
    require(sum(data['caption_health'].values())==len(inventory),'caption categories')
    for v in videos:
        r=v['responses']; total=r['total']
        require(type(total) is int and total>=0,'comment total')
        require(0<=r['human_reviewed']<=total,'reviewed comments')
        require(total==v['classified_comments'],'per-video comment count')
        require(total<=v['retained_comments'],'classified exceeds retained')
        require(bool(v.get('label')) or total==0,'comments without classified video')
        for field in ('alignment','sentiment'):
            require(all(type(n) is int and n>=0 for n in r[field].values()),field+' values')
            require(sum(r[field].values())==total,field+' sum')
        if 'alignment_sentiment' in r:
            joint=r['alignment_sentiment']
            require(sum(sum(row.values()) for row in joint.values())==total,'joint total')
            for key,n in r['alignment'].items():
                require(sum(joint.get(key,{}).values())==n,'joint alignment')
            for key,n in r['sentiment'].items():
                require(sum(row.get(key,0) for row in joint.values())==n,'joint sentiment')
    require(c['classified_comments']==sum(v['responses']['total'] for v in videos),'global comments')
    require(c['reviewed_comments']==sum(v['responses']['human_reviewed'] for v in videos),'global reviewed comments')
    require(c['retained_comments']==sum(v['retained_comments'] for v in videos),'global retained comments')


if __name__ == '__main__':
    import sys
    check(json.loads(Path(sys.argv[1]).read_text()))
    print('Public video and comment counts reconcile.')
