"""Mac recovery entry point. Private evidence never enters Git or console output."""
import argparse
from datetime import date, datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import sys
import ssl
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / 'private'
os.environ['HF_HOME'] = str(PRIVATE / 'whisper-cache')
os.environ['PYTHONPATH'] = str(ROOT / 'src')
sys.path.insert(0, str(ROOT / 'src'))
from eiim.audio_transcripts import AudioTranscripts
from eiim.core import digest
from eiim.storage import record

URL = 'https://monitor.hamelberg-ai.com/data.json'

def recover_queue(queue, save, progress, *, reader_factory=AudioTranscripts,
                  clock=time.monotonic, max_seconds=14400):
    """Continue normal chunk boundaries, but never retry an access block in a loop."""
    started = clock()
    completed = saved = chunks = 0
    reason = None
    reader = None
    def status(state):
        return {'status': state, 'attempted_sources': completed,
                'saved_transcripts': saved, 'remaining_eligible': len(queue)-completed,
                'chunks_started': chunks, 'stop_reason': reason,
                'updated_at': datetime.now(timezone.utc).isoformat()}
    while completed < len(queue):
        remaining_seconds = max_seconds - (clock()-started)
        if remaining_seconds <= 0:
            reason = 'session_time_limit'
            break
        if reader is None:
            reader = reader_factory(max_videos=80, max_seconds=min(2700, remaining_seconds))
            chunks += 1
        progress(status('running'))
        source = queue[completed]
        result = reader.check({'video_id': source['id'],
                               'original_audio_language': source.get('original_language', 'und')})
        if result is None:
            if reader.stopped == 'audio_run_limit' and reader.attempted:
                reader = None
                continue
            reason = reader.stopped or 'no_progress'
            break
        result['direct_failure_reason'] = 'RequestBlocked' if source.get('caption_state') == 'blocked' else None
        save(source, result)
        completed += 1
        saved += bool(result.get('transcript_english'))
        progress(status('running'))
        if reader.stopped and reader.stopped != 'audio_run_limit':
            reason = reader.stopped
            break
    if not reason:
        reason = 'eligible_queue_complete'
    final = status('complete' if reason == 'eligible_queue_complete' else 'paused')
    progress(final)
    return final

def save_progress(state):
    target = PRIVATE / 'local-recovery-state.json'
    temp = target.with_suffix('.new')
    temp.write_text(json.dumps(state, indent=2)+'\n')
    temp.chmod(0o600)
    temp.replace(target)

def retained(batch, today):
    if not re.fullmatch(r'\d{4}-W\d{2}', batch):
        return False
    try:
        end = date.fromisocalendar(int(batch[:4]), int(batch[6:]), 7)
        return today - timedelta(days=30) <= end <= today + timedelta(days=7)
    except ValueError:
        return False

def candidates(inventory, rows, now):
    latest = {}
    saved = set()
    for row in rows:
        r = row['record']; key = (r['batch_id'], r['video_id'])
        latest[key] = r['payload']
        if r['payload'].get('transcript_english'):
            saved.add(key)
    pending = []
    for source in inventory:
        key = (source['batch'], source['id'])
        if (not retained(source['batch'], now.date()) or source.get('caption_state') == 'saved'
                or key in saved or not re.fullmatch(r'[A-Za-z0-9_-]{11}', source['id'])):
            continue
        previous = latest.get(key)
        if previous:
            stamp = previous.get('audio_attempted_at')
            if not stamp:
                continue
            attempted = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
            quality = previous.get('failure_reason') in {'AudioLanguageUncertain', 'AudioNoUsableSpeech', 'AudioInvalidSegments'}
            if now - attempted < timedelta(days=7 if quality else 1):
                continue
        pending.append((bool(previous), source))
    return [s for _, s in sorted(pending, key=lambda x: x[0])]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', type=Path)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--max-session-seconds', type=int, default=14400)
    args = parser.parse_args()
    if not 1 <= args.max_session_seconds <= 14400:
        parser.error('--max-session-seconds must be between 1 and 14400')
    PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(PRIVATE, 0o700)
    os.chdir(ROOT)
    with (PRIVATE / 'local-recovery.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Recovery is already running'); return
        if args.snapshot:
            data = json.loads(args.snapshot.read_text())
        else:
            import certifi
            with urllib.request.urlopen(URL, timeout=60, context=ssl.create_default_context(cafile=certifi.where())) as response:
                raw = response.read(20_000_001)
                if len(raw) > 20_000_000:
                    raise ValueError('Public snapshot unexpectedly large')
                data = json.loads(raw)
        now = datetime.now(timezone.utc)
        stamp = datetime.fromisoformat(data['as_of'].replace('Z', '+00:00'))
        if now - stamp > timedelta(days=7):
            raise ValueError('Public snapshot is stale; investigate before recovery')
        output = PRIVATE / 'recovered-audio.jsonl'
        rows = [json.loads(x) for x in output.read_text().splitlines()] if output.exists() else []
        rows = [r for r in rows if retained(r['record']['batch_id'], now.date())]
        queue = candidates(data['inventory'], rows, now)
        print(json.dumps({'eligible_for_recovery': len(queue), 'retained_local_records': len(rows), 'dry_run': args.dry_run}), flush=True)
        if args.dry_run:
            return
        temp = output.with_suffix('.new')
        temp.write_text(''.join(json.dumps(r) + '\n' for r in rows))
        os.chmod(temp, 0o600)
        temp.replace(output)
        def save(source, result):
            row = record('pipeline_runs', source['batch'], source['batch'] + ':hybrid-caption:' + digest([source['id'], result]), result, source['id'])
            with output.open('a') as f:
                f.write(json.dumps(row) + '\n')
                f.flush()
                os.fsync(f.fileno())
        def progress(state):
            save_progress(state)
            print(json.dumps(state), flush=True)
        recover_queue(queue, save, progress, max_seconds=args.max_session_seconds)

if __name__ == '__main__':
    main()
