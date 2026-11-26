"""Continue proven pending work after deployment and source audit, never retry a failed job."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import urllib.request
from zoneinfo import ZoneInfo

GOVERNMENT='.github/workflows/government-news.yml'
BLOCKING={'government-news.yml','government-source-audit.yml','site.yml','retention.yml','recover-government-pages.yml'}
BRIEF='kedmahamelberg-ai/aieo-brief'


def plan(now,runs,brief_runs):
    local=now.astimezone(ZoneInfo('Europe/Amsterdam'))
    for hour in (9,15):
        target=local.replace(hour=hour,minute=0,second=0,microsecond=0)
        if -dt.timedelta(minutes=10)<=target-local<=dt.timedelta(minutes=150):
            return {'enabled':False,'reason':'Leave the upcoming regular collection window clear.'}
    active=[r for r in runs if r['status']!='completed' and r.get('path','').split('/')[-1] in BLOCKING]
    if active:return {'enabled':False,'reason':'A collection, audit or publication is active.'}
    if any(r['status']!='completed' and 'government' in r.get('name','').lower() for r in brief_runs):
        return {'enabled':False,'reason':'Brief government import or verification is active.'}
    eligible=[r for r in runs if r.get('path')==GOVERNMENT and r.get('head_branch')=='main']
    latest=max(eligible,key=lambda r:r['id'],default=None)
    if not latest or latest.get('conclusion')!='success':
        return {'enabled':False,'reason':'The latest main government run has not succeeded; do not retry it.'}
    return {'enabled':True,'run_id':latest['id'],'reason':'The previous government deployment and audit have finished.'}


def pending_work(state,run_id):
    progress=state.get('classification_progress') or {}
    if str(progress.get('run_id'))!=str(run_id) or progress.get('classified',0)<=0:
        return 0,'No successful classification progress was proved for this exact checkpoint.'
    if not state.get('calibration_complete'):
        return 0,'The researcher calibration gate is still pending.'
    items=[item for item in state.get('items',[]) if item.get('classification_status')=='pending_classification'
           and not item.get('classification_error') and not item.get('human_reviewed') and not item.get('source_reviewed')]
    return len(items),'Only fresh pending records without source or model errors are eligible.'


def github(path,body=None,*,public=False):
    headers={'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'EIIM-backlog/1.0'}
    if not public:headers['Authorization']='Bearer '+os.environ['GITHUB_TOKEN']
    payload=json.dumps(body).encode() if body is not None else None
    if payload is not None:headers['Content-Type']='application/json'
    request=urllib.request.Request('https://api.github.com'+path,headers=headers,data=payload)
    with urllib.request.urlopen(request,timeout=30) as response:
        if body is not None:
            if response.status!=204:raise RuntimeError('GitHub did not accept the classify-only dispatch')
            return None
        return json.load(response)


def preflight():
    repo=os.environ['GITHUB_REPOSITORY']
    runs=github(f'/repos/{repo}/actions/runs?per_page=100')['workflow_runs']
    brief=github(f'/repos/{BRIEF}/actions/runs?per_page=100',public=True)['workflow_runs']
    return plan(dt.datetime.now(dt.timezone.utc),runs,brief)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--dispatch',action='store_true');args=parser.parse_args()
    decision=preflight()
    if args.dispatch and decision['enabled']:
        if str(decision['run_id'])!=os.environ.get('EXPECTED_GOVERNMENT_RUN_ID'):
            decision={'enabled':False,'reason':'A newer government checkpoint superseded this plan.'}
        else:
            state=json.loads(Path('data/government_state.json').read_text())
            count,reason=pending_work(state,decision['run_id'])
            decision.update(pending=count,reason=reason,enabled=bool(count))
            if count:
                # Recheck after reading the checkpoint. Workflow-level serialization
                # is a final safeguard if an owner dispatch races this preflight.
                check=preflight()
                if not check['enabled'] or check['run_id']!=decision['run_id']:
                    decision=check;decision['enabled']=False
                else:
                    cutoff=dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
                    github(f"/repos/{os.environ['GITHUB_REPOSITORY']}/actions/workflows/government-news.yml/dispatches",
                           {'ref':'main','inputs':{'daily_phase':'retry','classify_only':True,'fresh_pending_only':True,'until':cutoff}})
                    decision['dispatched']=True
    print(json.dumps(decision))
    if not args.dispatch and os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a') as output:
            output.write('enabled='+str(decision['enabled']).lower()+'\n')
            if decision['enabled']:output.write('run_id='+str(decision['run_id'])+'\n')


if __name__=='__main__':main()
