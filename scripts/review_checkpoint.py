"""Credential-free private review preparation and validation from a fresh snapshot.

The connected Supabase tool supplies the snapshot and imports validated outbox
rows. This program never stores credentials or sends evidence to the public site.
"""
import argparse
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from eiim.storage import MemoryStore
from eiim.hybrid_review import packet, write_html, import_reviews

TABLES = ('weekly_batches', 'sampled_videos', 'candidate_videos', 'pipeline_runs', 'comments', 'human_validation')

class SnapshotStore(MemoryStore):
    def __init__(self, snapshot):
        super().__init__()
        stamp = datetime.fromisoformat(snapshot['as_of'].replace('Z', '+00:00'))
        age = datetime.now(timezone.utc) - stamp
        if age > timedelta(hours=24) or age < -timedelta(minutes=5):
            raise ValueError('A fresh retained database snapshot is required')
        missing = set(TABLES) - set(snapshot['tables'])
        if missing:
            raise ValueError('Incomplete review snapshot')
        for table in TABLES:
            rows = [r for r in snapshot['tables'][table] if not r.get('purged_at')]
            if table == 'weekly_batches':
                self.batches = {r['id']: r for r in rows}
            else:
                self.tables[table] = {r['id']: r for r in rows}
        self.outbox = []

    def write(self, batch, rows, stage=None):
        result = super().write(batch, rows, stage)
        self.outbox.extend(rows)
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--batch', required=True)
    parser.add_argument('--reviews', type=Path)
    args = parser.parse_args()
    private = ROOT / 'private'
    private.mkdir(mode=0o700, exist_ok=True)
    os.chmod(private, 0o700)
    store = SnapshotStore(json.loads(args.snapshot.read_text()))
    if args.batch not in store.batches:
        raise ValueError('Batch is no longer retained')
    if args.reviews:
        items = json.loads(args.reviews.read_text())
        if not isinstance(items, list) or not items:
            raise ValueError('Expected confirmed review list')
        result = import_reviews(store, items)
        target = private / 'review-outbox.json'
        target.write_text(json.dumps(store.outbox))
        os.chmod(target, 0o600)
        print(json.dumps(result))
    else:
        data = packet(store, args.batch)
        folder = private / 'review' / args.batch
        result = write_html(data, folder / 'index.html')
        for p in folder.iterdir():
            if p.is_file():
                os.chmod(p, 0o600)
        print(json.dumps({**result, 'assigned_videos': data['plan']['target'],
                          'assigned_comments': data['comment_plan']['target']}))

if __name__ == '__main__':
    main()
