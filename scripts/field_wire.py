"""Render dispatches from the two allowlisted public Monitor exports."""
from collections import Counter
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from hashlib import sha256
import shutil
from field_wire_preview import preview_data, draw_preview
from html import escape
from pathlib import Path
from string import Template
from urllib.parse import urlencode, quote
import json
import re


LIMIT = 8


def text(value):
    return escape(str(value), quote=True)


def day(record):
    return (record.get("published_date") or record.get("published_at") or "")[:10]


def government_dispatches(items):
    eligible = {row["id"]: row for row in items if row.get("related") is True
                and row.get("classification_status") in {"human_reviewed", "provisional"}
                and row.get("ticker_message") and day(row)}
    counts = Counter((r["country_code"], day(r)) for r in eligible.values())
    for row in sorted(eligible.values(), key=lambda r: (day(r), r.get("published_at") or "", r["id"]), reverse=True)[:LIMIT]:
        end = date.fromisoformat(day(row))
        days = [end - timedelta(days=i) for i in reversed(range(7))]
        code = row["country_code"]
        values = [counts[code, d.isoformat()] for d in days]
        bars = "".join(f'<i style="height:{100*v/max(1,max(values)):.1f}%"><span>{v}</span></i>' for v in values)
        graphic = (f'<figure class="activity"><b>{text(code)}</b><div class="pulse">{bars}</div>'
                   f'<figcaption>Related releases · {days[0]:%d %b}–{end:%d %b}</figcaption></figure>')
        # The ticker is the Monitor's short English editorial field.
        yield dict(date=day(row), desk=0, key="gov-"+row["id"], tag=row["country"], title=row["ticker_message"],
                   body="", graphic=graphic, href="/?"+urlencode({"record":row["id"]})+"#government")


def video_dispatches(videos):
    latest = {}
    for row in sorted(videos, key=lambda r: (r.get("batch") or "", (r.get("engagement") or {}).get("captured_at") or "")):
        latest[row["id"]] = row
    eligible = [r for r in latest.values() if (r.get("label") or {}).get("relevance") == "related"
                and day(r) and r.get("title")]
    ordered = sorted(eligible, key=lambda r: (day(r), r.get("published_at") or "", r["id"]), reverse=True)
    for row in [v for v in ordered if (v.get("video_synopsis") or "").strip()][:LIMIT]:
        summary = row["video_synopsis"].strip()
        graphic = (f'<figure class="cover"><img alt="" width="320" height="180" '
                   f'src="https://i.ytimg.com/vi/{quote(row["id"], safe="")}/mqdefault.jpg"></figure>')
        yield dict(date=day(row), desk=1, key="video-"+row["id"], tag=row["channel"], title=row["title"], body=summary,
                   graphic=graphic, href=video_link(row))
    samples = [r for r in eligible if (r.get("responses") or {}).get("total", 0) > 0]
    for row in sorted(samples, key=lambda r: (r["batch"], r.get("published_at") or "", r["id"]), reverse=True)[:LIMIT]:
        response = row["responses"]
        total = response["total"]
        yield dict(date=day(row), desk=2, key="comments-"+row["batch"]+"-"+row["id"],
                   tag=row["channel"], week=row["batch"], title=row["title"], context=row.get("video_synopsis"), total=total,
                   alignment=response["alignment"], href=video_link(row))



def video_link(row):
    return "/?" + urlencode({"record":row["id"], "week":row["batch"]}) + "#evidence"


def dispatch_row(row):
    desk = row["desk"]
    key = text(row["key"])
    anchor = text(row.get("anchor", row["key"]))
    source = text(row["href"])
    source_link = f'<a class="source" href="{source}">Source ↗</a>'
    lead = row.get("body") or row["title"]
    headline = f'<h3>{text(lead)}</h3>'
    if desk == 2:
        counts = row["alignment"]
        total = row["total"]
        support = counts.get("supports", 0)
        oppose = counts.get("opposes", 0)
        others = total - support - oppose
        details = ", ".join(f'{label.replace("_", " ")} {n}' for label, n in sorted(counts.items()))
        phrases = {"supports": "backed the message", "opposes": "opposed the message",
                   "mixed": "expressed mixed views", "unclear": "had unclear alignment",
                   "no_position": "took no position", "unrelated": "discussed something else"}
        peak = max(counts.values(), default=0)
        leaders = [k for k, n in counts.items() if n == peak]
        if len(leaders) == 1 and leaders[0] in phrases:
            insight = f'{counts[leaders[0]]} of {total} {phrases[leaders[0]]}.'
        else:
            insight = f'{support} backed the message and {oppose} opposed it ({total} sampled).'
        context = row.get("context") or re.sub(r"\s+#\S+", "", row["title"])
        return (f'<tr id="{anchor}" data-wire="{key}"><td class="copy"><h3>{text(insight)}</h3>'
                f'<p class="video-context">Video: {text(context)}</p>{source_link}'
                f'<small>{text(row["tag"])} · {text(row["week"])}</small></td>'
                f'<td class="num">{total}</td><td class="num positive">{support}</td>'
                f'<td class="num negative">{oppose}</td><td class="num" title="{text(details)}">{others}</td></tr>')
    label = "Gov" if desk == 0 else "Video"
    return (f'<tr id="{anchor}" data-wire="{key}" data-desk="{label}"><td class="stamp">'
            f'<time datetime="{text(row["date"])}">{date.fromisoformat(row["date"]):%d %b}</time>'
            f'<b>{label}</b></td><td class="copy">{headline}<small>{text(row["tag"])} · {source_link}</small></td>'
            f'<td class="visual">{row["graphic"]}</td></tr>')


BASE = "https://monitor.hamelberg-ai.com/field-wire/"
TEMPLATE = Template(Path(__file__).with_name("field_wire.html").read_text())


def render_page(path, rows, stamp, dated, chart, dates, earlier=()):
    news = sorted((r for r in rows if r["desk"] != 2), key=lambda r: r["date"], reverse=True)
    audience = [r for r in rows if r["desk"] == 2]
    edition_path = f"/field-wire/{stamp}/" if stamp else "/field-wire/"
    canonical = BASE + (stamp + "/" if dated else "")
    title = f"Field Wire · {stamp}" if dated else "Field Wire"
    preview_meta = figure = ""
    desc = "Security dispatches from government releases, YouTube videos and sampled audience comments."
    if chart:
        heading, sample, values, source, target = chart
        finding = sample + ". " + ", ".join(f"{name} {n:,}" for name, n in values) + "."
        desc = f"{stamp} · {finding}"
        image = BASE + stamp + "/preview.png"
        alt = text(f"{heading}. {finding}")
        preview_meta = (f'<meta property="og:image" content="{image}"><meta property="og:image:width" content="1280">'
                        f'<meta property="og:image:height" content="720"><meta property="og:image:alt" content="{alt}">'
                        f'<meta name="twitter:card" content="summary_large_image"><meta name="twitter:image" content="{image}">')
        figure = (f'<figure class="edition-chart"><a href="{image}"><img src="{image}" width="1280" height="720" '
                  f'loading="lazy" alt="{alt}"></a><figcaption><b>{text(heading)}</b> {text(finding)} '
                  f'<a href="{edition_path}#{target}">{text(source)}</a></figcaption></figure>')
    history = ""
    if dates:
        links = " ".join(f'<a href="/field-wire/{d}/">{d}</a>' for d in reversed(dates))
        history = f'<details class="history"><summary>Daily editions</summary><nav aria-label="Dated editions">{links}</nav></details>'
    earlier_html = ""
    if earlier:
        filings = []
        for row in earlier:
            # Keep the same table structure and source links for old share targets.
            headers = ("Report", "Total", "For", "Against", "Other") if row["desk"] == 2 else ("Filed", "Dispatch", "Visual")
            head = "".join(f'<th scope="col">{h}</th>' for h in headers)
            filings.append(f"<table><thead><tr>{head}</tr></thead><tbody>{dispatch_row(row)}</tbody></table>")
        earlier_html = '<section><h2>Earlier filings</h2>' + "".join(filings) + '</section>'
    path.write_text(TEMPLATE.substitute(
        title=text(title), canonical=canonical, description=text(desc), preview_meta=preview_meta,
        figure=figure, earlier=earlier_html, history=history, stamp=stamp, edition_path=edition_path,
        edition_link=f'<a href="{edition_path}">Edition · {stamp}</a>' if stamp else '',
        news=''.join(map(dispatch_row, news)) or '<tr><td colspan="3">Awaiting dispatches.</td></tr>',
        audience=''.join(map(dispatch_row, audience)) or '<tr><td colspan="5">Awaiting classified comments.</td></tr>',
        edition=max((r["date"] for r in rows), default="—"), count=len(news), samples=len(audience)))


def render(out, research, government, archive, today=None):
    stamp = (today or datetime.now(ZoneInfo("Europe/Amsterdam")).date()).isoformat()
    rows = list(government_dispatches(government.get("items", [])))
    rows.extend(video_dispatches(research.get("videos", [])))
    output = out / "field-wire"
    output.mkdir(exist_ok=True)
    archive.mkdir(parents=True, exist_ok=True)
    dates = sorted(p.name for p in archive.iterdir() if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.name))
    chart = None
    if rows:
        folder = archive / stamp
        folder.mkdir(exist_ok=True)
        ledger = folder / "rows.json"
        saved = json.loads(ledger.read_text()) if ledger.exists() else {}
        # Keep an earlier version addressable when a classification or summary changes during the day.
        for row in rows:
            key = row["key"]
            if key in saved and saved[key] != row:
                version = sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()[:12]
                row["anchor"] = key + "-" + version
            saved[row.get("anchor", key)] = row
        ledger.write_text(json.dumps(saved, ensure_ascii=False, sort_keys=True) + "\n")
        if stamp not in dates:
            dates.append(stamp)
        current = {r.get("anchor", r["key"]) for r in rows}
        earlier = [r for k, r in saved.items() if k not in current]
        # Each video contributes its currently filed sample once to the graphic.
        chart = preview_data(rows)
        draw_preview(folder / "preview.png", stamp, chart)
        render_page(folder / "index.html", rows, stamp, True, chart, [], earlier)
    keys = set()
    for d in dates:
        folder = archive / d
        public = output / d
        public.mkdir(exist_ok=True)
        for asset in ("index.html", "preview.png"):
            shutil.copyfile(folder / asset, public / asset)
        keys.update(r["key"] for r in json.loads((folder / "rows.json").read_text()).values())
    render_page(output / "index.html", rows, stamp if rows else "", False, chart, dates)
    (output / "items.json").write_text(json.dumps(sorted(keys)))
    return dates
