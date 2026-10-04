"""Copy only public assets; research source and secrets never enter Pages output."""

import json, shutil, sys
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
    from eiim.cli import export_public
    from eiim.storage import Store

    print(export_public(Store(), out / "data.json"))
print("Public website built in build/")
