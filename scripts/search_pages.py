"""Build search-friendly summaries from public Monitor material."""
from datetime import date
from pathlib import Path
from string import Template
from html import escape
from hashlib import sha256
import json
import re
from urllib.parse import urlsplit
from xml.sax.saxutils import escape as xml_escape

BASE = "https://monitor.hamelberg-ai.com"


def source_date(value):
    try:
        return date.fromisoformat(str(value or "")[:10]).isoformat()
    except ValueError:
        return ""


def display_date(value):
    when = date.fromisoformat(value)
    return f"{when.day} {when:%B %Y}"


def public_link(source):
    url = source["url"]
    if not (url.startswith("/") and not url.startswith("//")):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username:
            raise ValueError("Expected a public source URL")
    return f'<a href="{escape(url, quote=True)}">{escape(source["label"])}</a>'


ARTICLE = Template("""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>$title | European Security Monitor</title>
<meta name="description" content="$description">
<link rel="canonical" href="$canonical">
<meta property="og:type" content="article"><meta property="og:title" content="$title">
<meta property="og:description" content="$description"><meta property="og:url" content="$canonical">
<link rel="stylesheet" href="/style.css"><link rel="icon" href="/assets/favicon.png">
<script type="application/ld+json">$schema</script></head>
<body><main class="methodology"><nav aria-label="Monitor"><a href="/">European Security Monitor</a> ·
<a href="/field-wire/">Field Wire</a> · <a href="/research.html">Research methods</a></nav>
<article><p class="eyebrow">$section</p><h1>$title</h1><p><time datetime="$source_date">$date_label</time></p>
<p data-finding-views hidden></p><p>$description</p>$body<h2>Sources</h2>$links</article></main></body></html>
""")


def build_findings(out: Path, data_file: Path):
    entries = json.loads(data_file.read_text())
    for story in entries:
        slug = story["slug"]
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
            raise ValueError("Invalid finding slug")
        path = f"/findings/{slug}/"
        canonical = BASE + path
        links = "".join(f'<li>{public_link(link)}</li>' for link in story["sources"])
        source_urls = [s["url"] if s["url"].startswith("https://") else BASE + s["url"]
                       for s in story["sources"]]
        schema = {
            "@context": "https://schema.org", "@type": "Article",
            "headline": story["title"], "description": story["description"],
            "mainEntityOfPage": canonical,
            "about": story["section"], "citation": source_urls, "datePublished": story["published"],
            "publisher": {"@type": "Organization", "name": "European Security Monitor", "url": BASE},
        }
        target = out / path.strip("/") / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(ARTICLE.substitute(
            title=escape(story["title"]), description=escape(story["description"]), canonical=canonical,
            schema=json.dumps(schema, ensure_ascii=False).replace("<", r"\u003c"),
            section=escape(story["section"]), source_date=story["source_date"],
            date_label=display_date(story["source_date"]),
            body="".join(f"<p>{escape(p)}</p>" for p in story["paragraphs"]), links=f"<ul>{links}</ul>"))
        story["path"] = path
    return entries


def coverage_summary(research, government, editions, findings):
    dates = []
    for label, records in (("Government releases through", government.get("items", [])),
                           ("Sampled videos through", research.get("videos", []))):
        latest = max((source_date(row.get("published_date") or row.get("published_at"))
                      for row in records), default="")
        if latest:
            dates.append(f'{label} <time datetime="{latest}">{display_date(latest)}</time>')
    date_line = f'<p class="small">{" · ".join(dates)}</p>' if dates else ""
    links = []
    if editions:
        latest = max(editions)
        links.append(f'<a href="/field-wire/{latest}/">Field Wire for {display_date(latest)}</a>')
    links.extend(f'<a href="{entry["path"]}">{escape(entry["title"])}</a>' for entry in findings)
    list_html = "".join(f"<li>{link}</li>" for link in links)
    return (
        '<section class="panel monitor-coverage" aria-labelledby="monitor-coverage-heading">'
        '<div class="panel-heading"><h2 id="monitor-coverage-heading">Research and recent findings</h2></div>'
        '<div class="panel-body"><p>The Monitor compares how official government statements and public '
        'YouTube videos describe European security, and how sampled comments respond to those videos. '
        'Read the dated findings, follow the original sources, and '
        '<a href="/research.html">see how the evidence is collected</a>.</p>'
        f'{date_line}<ul>{list_html}</ul></div></section>'
    )


def add_page_view_script(out, findings, editions):
    assets = ["analytics.js", "visitor-count.js", "page-views.js"]
    tags = []
    for asset in assets:
        version = sha256((out / asset).read_bytes()).hexdigest()[:12]
        tags.append(f'<script defer src="/{asset}?v={version}"></script>')
    # Saved Field Wire editions can already include an earlier copy of the tag.
    existing = re.compile(r'<script\b[^>]*\bsrc="/?(?:analytics|visitor-count|page-views)\.js(?:\?[^"]*)?"[^>]*></script>')
    pages = ["index.html", "about.html", "contact.html", "research.html", "privacy.html", "field-wire/index.html"]
    pages.extend(f"field-wire/{stamp}/index.html" for stamp in editions)
    pages.extend(entry["path"].strip("/") + "/index.html" for entry in findings)
    for name in pages:
        target = out / name
        html = target.read_text()
        if html.count("</head>") != 1:
            raise ValueError(f"{name} must have one closing head tag")
        target.write_text(existing.sub("", html).replace("</head>", "".join(tags) + "</head>"))


def sitemap(paths):
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join(f"<url><loc>{xml_escape(BASE + path)}</loc></url>" for path in paths)
            + "</urlset>")
