"""Copy only public assets; research source and secrets never enter Pages output."""

import hashlib, json, shutil, sys, os
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
if "--live" in sys.argv:
    sys.path.insert(0, str(ROOT / "src"))
    from eiim.hybrid_public import export_public
    from eiim.storage import Store

    print(export_public(Store(), out / "data.json"))
if "--live" in sys.argv:
    from check_cameras import refresh
    refresh(out / "cameras.json", os.environ.get("YOUTUBE_API_KEY"))
# Bind code, styles and the data snapshot to one deployment revision.
revision = hashlib.sha256(
    b"".join((out / name).read_bytes() for name in ["map-data.js", "app.js", "live.js", "style.css", "data.json", "cameras.json"])
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
print("Public website built in build/")
