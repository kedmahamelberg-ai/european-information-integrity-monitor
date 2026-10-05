"""Refresh only camera availability metadata; never fetch or store media."""
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def camera_status(item):
    if not item:
        return 'unavailable'
    if not item.get('status', {}).get('embeddable'):
        return 'embedding_disabled'
    live = item.get('liveStreamingDetails', {})
    if (item.get('snippet', {}).get('liveBroadcastContent') == 'live'
            and live.get('actualStartTime') and not live.get('actualEndTime')):
        return 'live'
    return 'not_live'


def refresh(path, key):
    catalogue = json.loads(path.read_text())
    if not key:
        print('Camera check: no API key; retaining dated catalogue (client expires it after 48 hours).')
        return
    checked = datetime.now(timezone.utc).isoformat()
    query = urllib.parse.urlencode({'part': 'snippet,status,liveStreamingDetails',
        'id': ','.join(c['video_id'] for c in catalogue['cameras']), 'key': key})
    try:
        with urllib.request.urlopen('https://www.googleapis.com/youtube/v3/videos?' + query, timeout=25) as response:
            items = {x['id']: x for x in json.load(response).get('items', [])}
        for camera in catalogue['cameras']:
            camera.update(status=camera_status(items.get(camera['video_id'])),
                          checked_at=checked, verification='YouTube Data API live and embeddable metadata')
    except Exception:
        # Do not log a URL containing the API key or call an old stream live.
        for camera in catalogue['cameras']:
            camera.update(status='unverified', checked_at=checked)
        print('::warning::Camera availability check failed; streams marked unverified.')
    catalogue['checked_at'] = checked
    path.write_text(json.dumps(catalogue, ensure_ascii=False, indent=2) + '\n')
    print('Camera check:', sum(c['status']=='live' for c in catalogue['cameras']), 'live of', len(catalogue['cameras']))


if __name__ == '__main__':
    refresh(Path('build/cameras.json'), os.environ.get('YOUTUBE_API_KEY'))
