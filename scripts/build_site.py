"""Copy only public assets; research source and secrets never enter Pages output."""

import hashlib, json, shutil, sys, os, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / "apps/dashboard"
out = ROOT / "build"
out.mkdir(exist_ok=True)
for p in source.rglob("*"):
    if p.is_file():
        dst = out / p.relative_to(source)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst)
(out / ".nojekyll").write_text("")
gov_state = ROOT / "data" / "government_state.json"
gov_public = out / "government-data.json"
if gov_state.exists() and not gov_public.exists():
    snapshot = json.loads(gov_state.read_text())
    gov_public.write_text(json.dumps({"as_of": snapshot.get("last_successful_collection_end"), "items": [{k: v for k, v in item.items() if k != "english_translation"} for item in snapshot.get("items", [])]}, ensure_ascii=False, indent=2) + "\n")
elif not gov_public.exists():
    gov_public.write_text('{"items":[]}\n')
if "--live" in sys.argv:
    sys.path.insert(0, str(ROOT / "src"))
    from eiim.hybrid_public import export_public
    from eiim.storage import Store

    # Publication needs only transcript-access, engagement, translations,
    # recovery health and hybrid labels from pipeline_runs. Ask Supabase for
    # that bounded projection instead of transferring model/cache envelopes.
    print(export_public(Store(public_pipeline_only=True), out / "data.json"))
if "--camera-only" in sys.argv:
    # A camera availability refresh must preserve the already published research
    # snapshot; never query Supabase merely to check independent city streams.
    timestamp = int(datetime.now(timezone.utc).timestamp())
    request = urllib.request.Request(
        f"https://monitor.hamelberg-ai.com/data.json?camera-refresh={timestamp}",
        headers={"Cache-Control": "no-cache", "User-Agent": "EIIM-camera-refresh/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read(10_000_001)
    if len(payload) > 10_000_000:
        raise RuntimeError("Published research snapshot exceeds camera refresh limit")
    published = json.loads(payload)
    if not isinstance(published, dict) or not isinstance(published.get("videos"), list):
        raise RuntimeError("Published research snapshot is invalid")
    (out / "data.json").write_bytes(payload)
if "--live" in sys.argv or "--camera-only" in sys.argv:
    from check_cameras import refresh
    refresh(out / "cameras.json", os.environ.get("YOUTUBE_API_KEY"),
            strict="--camera-only" in sys.argv)
from check_public_counts import check
check(json.loads((out / "data.json").read_text()))
# Bind code, styles and the data snapshot to one deployment revision.
revision = hashlib.sha256(
    b"".join((out / name).read_bytes() for name in ["map-data.js", "app.js", "live.js", "style.css", "data.json", "cameras.json", "government-data.json"])
).hexdigest()[:16]
page = out / "index.html"
html = page.read_text().replace(
    '<html lang="en">', f'<html lang="en" data-build="{revision}">'
)
html = html.replace('src="app.js"', f'src="app.js?v={revision}"').replace(
    'href="style.css"', f'href="style.css?v={revision}"'
)
html = html.replace('src="live.js"', f'src="live.js?v={revision}"')
html = html.replace('src="map-data.js"', f'src="map-data.js?v={revision}"')
page.write_text(html)
# A stable, server-rendered authorship page is readable without JavaScript.
about = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>About the European Security Monitor | Kedma Hamelberg</title>
<meta name="description" content="The European Security Monitor is an independent research project created and developed by Kedma Hamelberg, PhD.">
<meta name="author" content="Kedma Hamelberg">
<link rel="canonical" href="https://monitor.hamelberg-ai.com/about.html">
<link rel="stylesheet" href="style.css?v=REV"></head><body>
<main class="methodology"><p><a href="./">Open the European Security Monitor</a></p>BODY</main>
</body></html>""".replace("REV", revision).replace("BODY", (out / "methodology.html").read_text())
(out / "about.html").write_text(about)
(out / "robots.txt").write_text("User-agent: *\nAllow: /\nSitemap: https://monitor.hamelberg-ai.com/sitemap.xml\n")
(out / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://monitor.hamelberg-ai.com/</loc></url><url><loc>https://monitor.hamelberg-ai.com/about.html</loc></url></urlset>')
print("Public website built in build/")
