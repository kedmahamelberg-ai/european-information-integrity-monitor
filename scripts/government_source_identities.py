"""Publisher-verified URL renames, shared by collection and publication QA."""
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

REGISTRY = Path(__file__).resolve().parents[1] / 'config/government_source_identities.json'


def load_identities():
    aliases, stable_ids = {}, {}
    for row in json.loads(REGISTRY.read_text())['identities']:
        preferred = row['preferred_url']
        ident = row['id']
        if not re.fullmatch(r'[a-f0-9]{20}', ident):
            raise ValueError('Invalid stable publisher record ID')
        if row['evidence'] != 'http_200_redirect_and_matching_publisher_canonical':
            raise ValueError('Unverified publisher identity')
        for url in [preferred, *row['aliases']]:
            parts = urlsplit(url)
            if (parts.scheme != 'https' or parts.hostname != 'www.stjornarradid.is'
                    or not parts.path.startswith('/efst-a-baugi/frettir/stok-frett/')):
                raise ValueError('Publisher identity is outside its verified source')
            key = url.rstrip('/')
            if key in aliases and aliases[key] != preferred:
                raise ValueError('Conflicting publisher URL identities')
            aliases[key] = preferred
        if preferred in stable_ids and stable_ids[preferred] != ident:
            raise ValueError('Conflicting stable publisher IDs')
        stable_ids[preferred] = ident
    return aliases, stable_ids


URL_ALIASES, STABLE_IDS = load_identities()


def resolved_source_url(url):
    if url.startswith('https://www.stjornarradid.is/efst-a-baugi/frettir/stok-frett/'):
        url = url.rstrip('/')
    return URL_ALIASES.get(url, url)
