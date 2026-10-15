"""Refresh only camera availability metadata; never fetch or store media."""
import json
import os
import re
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


def watch_status(page):
    """Catch YouTube's offline slate, which can coexist with isLiveNow=true."""
    match = re.search(r'"playabilityStatus":\{"status":"([A-Z_]+)"', page)
    if not match:
        return 'unverified'
    if match.group(1) == 'LIVE_STREAM_OFFLINE':
        return 'not_live'
    if match.group(1) != 'OK':
        return 'unavailable'
    return 'live' if '"isLiveNow":true' in page else 'not_live'


def check_watch_page(video_id):
    request = urllib.request.Request(
        'https://www.youtube.com/watch?v=' + urllib.parse.quote(video_id),
        headers={'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'en'},
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        page = response.read(2_000_000).decode('utf-8', errors='replace')
    return watch_status(page)


def refresh(path, key, *, strict=False):
    catalogue = json.loads(path.read_text())
    if not key:
        if strict:
            raise RuntimeError('Camera refresh requires YOUTUBE_API_KEY')
        print('Camera check: no API key; retaining dated catalogue (client expires it after 48 hours).')
        return
    checked = datetime.now(timezone.utc).isoformat()
    query = urllib.parse.urlencode({'part': 'snippet,status,liveStreamingDetails',
        'id': ','.join(c['video_id'] for c in catalogue['cameras']), 'key': key})
    try:
        with urllib.request.urlopen('https://www.googleapis.com/youtube/v3/videos?' + query, timeout=25) as response:
            items = {x['id']: x for x in json.load(response).get('items', [])}
        for camera in catalogue['cameras']:
            status = camera_status(items.get(camera['video_id']))
            if status == 'live':
                try:
                    status = check_watch_page(camera['video_id'])
                except Exception:
                    status = 'unverified'
            camera.update(status=status, checked_at=checked,
                          verification='YouTube Data API and public watch-page playback status')
    except Exception:
        if strict:
            raise RuntimeError('Camera availability check failed; keeping the last published directory') from None
        # Do not log a URL containing the API key or call an old stream live.
        for camera in catalogue['cameras']:
            camera.update(status='unverified', checked_at=checked)
        print('::warning::Camera availability check failed; streams marked unverified.')
    catalogue['checked_at'] = checked
    path.write_text(json.dumps(catalogue, ensure_ascii=False, indent=2) + '\n')
    print('Camera check:', sum(c['status']=='live' for c in catalogue['cameras']), 'live of', len(catalogue['cameras']))


if __name__ == '__main__':
    refresh(Path('build/cameras.json'), os.environ.get('YOUTUBE_API_KEY'))
