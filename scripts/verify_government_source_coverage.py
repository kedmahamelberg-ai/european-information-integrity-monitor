"""Check saved archive identities against the live Monitor; never call a model."""
from __future__ import annotations

import json
import os
from pathlib import Path
import time
import urllib.request

from government_coverage import index_records, publisher_identity

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'build/government-source-coverage.json'


def verify(report, snapshot, expected=None):
    if not isinstance(snapshot.get('items'),list) or not snapshot.get('as_of'):
        raise ValueError('Live government snapshot is invalid')
    sources=report.get('sources') or []
    codes=[row['country_code'] for row in sources]
    if set(codes)!=set(report.get('active_country_codes',[])) or len(codes)!=len(set(codes)):
        raise ValueError('Archive coverage report omits or duplicates an attempted country')
    if set(codes)&set(report.get('disabled_country_codes',[])):
        raise ValueError('A disabled country was included in the collection')
    ids=[item['id'] for item in snapshot['items']]
    if len(ids)!=len(set(ids)):
        raise ValueError('Live government data contains duplicate record IDs')
    owners={};duplicated=set()
    for item in snapshot['items']:
        keys={publisher_identity(item['country_code'],url) for url in [item['url'],*(item.get('source_aliases') or [])]}
        for key in keys:
            if key in owners and owners[key]!=item['id']:duplicated.add(key)
            else:owners[key]=item['id']
    if duplicated:
        raise ValueError('Duplicate publisher communications: '+', '.join(sorted(duplicated)[:8]))
    index=index_records(snapshot['items'])
    missing=[]; unverified=[]; total=0
    for row in sources:
        if row['status']!='complete':
            unverified.append({'country_code':row['country_code'],'source_url':row['source_url'],
                               'error':row.get('error') or row['status']})
            continue
        archive_records=row.get('archive_records')
        if not isinstance(archive_records,list) or len(archive_records)!=row['archive_unique_records']:
            raise ValueError('Archive proof lacks exact record identities: '+row['country_code'])
        total+=len(archive_records)
        for record in archive_records:
            item=index.get(publisher_identity(row['country_code'],record['url']))
            if item is None or item['id']!=record['id']:
                missing.append({'country_code':row['country_code'],**record})
    result={'monitor_as_of':snapshot['as_of'],'archive_records_checked':total,
            'verified_country_count':len(sources)-len(unverified),
            'attempted_country_count':len(sources),'unverified_sources':unverified,
            'missing_records':missing,'retained_records':len(ids),
            'complete':not unverified and not missing}
    if missing:
        raise ValueError('Official archive records absent from live Monitor: '+json.dumps(missing[:8]))
    if expected is not None:
        if snapshot['as_of']!=expected['as_of']:
            raise ValueError('The live government deployment does not match the saved publication cutoff')
        saved={item['id']:item for item in expected['items']}
        live={item['id']:item for item in snapshot['items']}
        changed=[]
        for ident in sorted(set(saved)|set(live)):
            left=saved.get(ident,{});right=live.get(ident,{})
            fields=sorted(key for key in set(left)|set(right) if left.get(key)!=right.get(key))
            if fields:changed.append({'id':ident,'source_url':left.get('url') or right.get('url'),'fields':fields})
        if changed:raise ValueError('Live government fields differ from the saved publication: '+json.dumps(changed[:8]))
        result['saved_publication_fields_match']=True
    return result


def main():
    if not REPORT.exists():
        raise SystemExit('Archive coverage proof is missing; a collection is required')
    report=json.loads(REPORT.read_text())
    request=urllib.request.Request('https://monitor.hamelberg-ai.com/government-data.json?coverage='+str(int(time.time())),
        headers={'Cache-Control':'no-cache','User-Agent':'EIIM-source-coverage/1.0'})
    result_path=ROOT/'government-source-coverage-check.json'
    try:
        with urllib.request.urlopen(request,timeout=45) as response:
            payload=response.read(25_000_001)
        if len(payload)>25_000_000:
            raise ValueError('Live government snapshot exceeds the bounded 25 MB limit')
        expected=json.loads((ROOT/'government-expected-data.json').read_text())
        result=verify(report,json.loads(payload),expected)
    except Exception as error:
        result_path.write_text(json.dumps({'complete':False,'verification_error':str(error)},ensure_ascii=False,indent=2)+'\n')
        raise
    result_path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    for source in result['unverified_sources']:
        print('::warning::Official archive coverage remains unverified: '+source['country_code'])
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as out:
            out.write(f"Archive coverage: {result['verified_country_count']}/{result['attempted_country_count']} sources verified; "
                      f"{result['archive_records_checked']} official archive identities matched live records. "
                      'URL coverage does not complete the separate original-source editorial audit.\n')


if __name__=='__main__':
    main()
