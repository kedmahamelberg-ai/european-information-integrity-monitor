"""Short-lived YouTube-only Netscape cookies from an Actions secret."""
import os
from pathlib import Path
import sys
import time


def cookie_file():
    value = os.environ.get('EIIM_YOUTUBE_COOKIE_FILE')
    return value if value and Path(value).is_file() else None


def youtube_cookies(text, at=None):
    at = time.time() if at is None else at
    lines = text.lstrip('\ufeff').splitlines()
    if not lines or lines[0].strip() not in {'# Netscape HTTP Cookie File', '# HTTP Cookie File'}:
        raise ValueError('YouTube cookies must use Netscape cookies.txt format')
    kept = []
    for line in lines[1:]:
        if not line.strip() or (line.startswith('#') and not line.startswith('#HttpOnly_')):
            continue
        parts = line.split('\t')
        if len(parts) != 7:
            raise ValueError('Invalid cookies.txt row; cookie values are not logged')
        domain = parts[0].removeprefix('#HttpOnly_').lstrip('.').lower()
        if domain != 'youtube.com' and not domain.endswith('.youtube.com'):
            continue
        if parts[1] not in {'TRUE', 'FALSE'} or parts[3] not in {'TRUE', 'FALSE'} or not parts[4].isdigit() or not parts[5] or not parts[6]:
            raise ValueError('Invalid YouTube cookie fields; values are not logged')
        expiry = int(parts[4])
        if expiry and expiry <= at:
            continue
        kept.append(line)
    if not kept:
        raise ValueError('No unexpired YouTube cookies found; refresh the GitHub secret')
    return '# Netscape HTTP Cookie File\n' + '\n'.join(kept) + '\n'


def prepare():
    secret = os.environ.pop('EIIM_YOUTUBE_COOKIES', '')
    if not secret.strip():
        print('YouTube cookie secret absent; public audio access only')
        return
    content = youtube_cookies(secret)
    target = Path(os.environ['EIIM_YOUTUBE_COOKIE_FILE'])
    # Create only a new private file. Never follow or overwrite an existing path.
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(content)
    print('YouTube cookie file configured for this job; contents remain private')


def cleanup():
    value = os.environ.get('EIIM_YOUTUBE_COOKIE_FILE')
    if value:
        Path(value).unlink(missing_ok=True)


if __name__ == '__main__':
    try:
        if sys.argv[1:] == ['cleanup']:
            cleanup()
        elif not sys.argv[1:]:
            prepare()
        else:
            raise ValueError('Unknown session-file operation')
    except (OSError, ValueError, KeyError):
        print('YouTube session file could not be prepared or removed; verify the secret format and runner path', file=sys.stderr)
        raise SystemExit(1) from None
