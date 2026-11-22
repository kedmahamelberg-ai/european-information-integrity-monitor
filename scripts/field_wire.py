"""Render dispatches from the two allowlisted public Monitor exports."""
from collections import Counter
from datetime import date, timedelta
from html import escape
from pathlib import Path
from string import Template
from urllib.parse import urlencode, quote
import json
import re


DESKS = ("What governments say", "Voices on YouTube", "What viewers say")
LIMIT = 8


def text(value):
    return escape(str(value), quote=True)


def day(record):
    return (record.get("published_date") or record.get("published_at") or "")[:10]


def topic_names(record, labels):
    return [labels.get(code, code.replace("_", " ")) for code in record.get("topics", [])]


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
                   body="", graphic=graphic, href="../?"+urlencode({"record":row["id"]})+"#government")


def video_dispatches(videos, labels):
    latest = {}
    for row in sorted(videos, key=lambda r: (r.get("batch") or "", (r.get("engagement") or {}).get("captured_at") or "")):
        latest[row["id"]] = row
    eligible = [r for r in latest.values() if (r.get("label") or {}).get("relevance") == "related"
                and day(r) and r.get("title")]
    ordered = sorted(eligible, key=lambda r: (day(r), r.get("published_at") or "", r["id"]), reverse=True)
    for row in ordered[:LIMIT]:
        topics = topic_names(row["label"], labels)
        summary = f'The Monitor codes this video under {", ".join(topics[:3])}.' if topics else "The Monitor classified this video as security related."
        if row.get("video_synopsis"):
            sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z“])", row["video_synopsis"].strip())
            summary = " ".join(sentences[:3])
        graphic = (f'<figure class="cover"><img alt="" width="320" height="180" '
                   f'src="https://i.ytimg.com/vi/{quote(row["id"], safe="")}/mqdefault.jpg"></figure>')
        yield dict(date=day(row), desk=1, key="video-"+row["id"], tag=row["channel"], title=row["title"], body=summary,
                   graphic=graphic, href=video_link(row))
    samples = [r for r in eligible if (r.get("responses") or {}).get("total", 0) > 0]
    for row in sorted(samples, key=lambda r: (r["batch"], r.get("published_at") or "", r["id"]), reverse=True)[:LIMIT]:
        response = row["responses"]
        total = response["total"]
        bars = []
        for label, count in sorted(response["alignment"].items(), key=lambda pair: -pair[1]):
            bars.append(f'<div><span>{text(label.replace("_"," "))}</span><meter min="0" max="{total}" value="{count}"></meter><b>{count}</b></div>')
        summary = (f'Of {total} classified comments, {response["alignment"].get("supports",0)} supported '
                   f'the video’s main message and {response["alignment"].get("opposes",0)} opposed it.')
        graphic = '<figure class="responses">'+''.join(bars)+'<figcaption>Alignment in the sampled comments</figcaption></figure>'
        yield dict(date=day(row), desk=2, key="comments-"+row["batch"]+"-"+row["id"], tag=row["batch"], title=row["title"], body=summary,
                   graphic=graphic, href=video_link(row))


def video_link(row):
    return "../?" + urlencode({"record":row["id"], "week":row["batch"]}) + "#evidence"


def card(row, poster=False):
    link = text(row["href"])
    meta = text(row["tag"])
    if row["desk"] == 2:
        meta += " · video published"
    heading = "h3" if poster else "h2"
    body = f'<p>{text(row["body"])}</p>' if row["body"] else ""
    graphic = row["graphic"] if poster else ""
    anchor = '' if poster else f' id="{text(row["key"])}"'
    return (f'<article{anchor} data-wire="{text(row["key"])}">{graphic}<div class="copy"><small>{meta} · <time>{text(row["date"])}</time></small>'
            f'<{heading}>{text(row["title"])}</{heading}>{body}'
            f'<a href="{link}">Monitor source ↗</a></div></article>')


def render(out, research, government):
    rows = list(government_dispatches(government.get("items", [])))
    rows.extend(video_dispatches(research.get("videos", []), research.get("topic_labels", {})))
    posters = []
    for i, name in enumerate(DESKS):
        stories = [card(row, True) for row in rows if row["desk"] == i]
        posters.append(f'<section class="poster desk-{i}"><h2>{name}</h2>'
                       + '<div class="frames">' + ''.join(stories) + '</div>'
                       + ('' if stories else '<p>No eligible records in this snapshot.</p>') + '</section>')
    entries = []
    for row in sorted(rows, key=lambda row: row["date"], reverse=True):
        entries.append(f'<div class="entry"><strong>{DESKS[row["desk"]]}</strong>{card(row)}</div>')
    template = Template(Path(__file__).with_name("field_wire.html").read_text())
    output = out / "field-wire"
    output.mkdir(exist_ok=True)
    (output / "items.json").write_text(json.dumps([row["key"] for row in rows]))
    (output / "index.html").write_text(template.substitute(
        posters=''.join(posters), entries=''.join(entries) or '<p>Awaiting the first dispatch.</p>'))
