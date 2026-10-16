"""Collect public national-government news, translate it, and classify narratives."""
import argparse
import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = json.loads((ROOT / "config/government_sources.json").read_text())["sources"]
LABELS = json.loads((ROOT / "config/narratives.json").read_text())["labels"]
STATE = ROOT / "data/government_state.json"
PUBLIC = ROOT / "build/government-data.json"
CORRECTIONS = ROOT / "data/government_corrections.json"
REVIEW_QUEUE = ROOT / "build/government-review-queue.json"
UA = "EuropeanSecurityMonitor/1.0 (public research; contact: monitor@hamelberg-ai.com)"


class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.text=[]; self.capture=0
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if tag == "a" and a.get("href"): self.links.append((a["href"], a.get("type", "")))
        if tag == "link" and a.get("href") and ("alternate" in a.get("rel", "").lower() or "rss" in a.get("type", "").lower() or "atom" in a.get("type", "").lower()): self.links.append((a["href"], a.get("type", "")))
        if tag in ("p", "article", "main", "h1", "h2"): self.capture += 1
    def handle_endtag(self, tag):
        if tag in ("p", "article", "main", "h1", "h2"): self.capture=max(0,self.capture-1)
    def handle_data(self, data):
        if data.strip(): self.text.append(data.strip())


def fetch(url, limit=2_000_000):
    req=urllib.request.Request(url, headers={"User-Agent":UA,"Accept":"text/html,application/rss+xml,application/atom+xml,application/xml,*/*"})
    with urllib.request.urlopen(req, timeout=25) as r:
        if r.status >= 400: raise RuntimeError(f"HTTP {r.status}")
        return r.geturl(), r.read(limit)


def date_value(value):
    if not value: return None
    try: return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt.timezone.utc)
    except ValueError:
        try: return email.utils.parsedate_to_datetime(value).astimezone(dt.timezone.utc)
        except (TypeError, ValueError): return None


def local_name(tag): return tag.rsplit("}",1)[-1].lower()


def parse_feed(body, base, country):
    root=ET.fromstring(body); entries=[]
    for node in root.iter():
        if local_name(node.tag) not in {"item","entry"}: continue
        fields={local_name(ch.tag):ch for ch in node}
        def val(key):
            el=fields.get(key); return "" if el is None else " ".join("".join(el.itertext()).split())
        link=val("link")
        el=fields.get("link")
        if el is not None: link=el.attrib.get("href",link)
        link=urllib.parse.urljoin(base, html.unescape(link))
        title=val("title")
        summary=val("description") or val("summary") or val("content")
        published=val("published") or val("updated") or val("pubdate") or val("date")
        if title and link: entries.append({"country":country["name"],"country_code":country["iso2"],"url":link,"title":re.sub("<[^>]+>"," ",html.unescape(title)).strip(),"published_at":published,"text":re.sub(r"\s+"," ",html.unescape(re.sub("<[^>]+>"," ",summary))).strip()})
    return entries


def discover(country):
    final, page=fetch(country["url"])
    parser=Links(); parser.feed(page.decode("utf-8","replace"))
    feeds=[]
    for href, typ in parser.links:
        u=urllib.parse.urljoin(final,href)
        if "rss" in typ.lower() or "atom" in typ.lower() or re.search(r"(rss|feed|atom)(\.xml)?/?$",u,re.I): feeds.append(u)
    feeds += [urllib.parse.urljoin(final,p) for p in ("news/rss.xml","news.rss","news.atom","rss.xml","rss","feed","news/feed/")]
    seen=set(); entries=[]
    for feed in feeds:
        if feed in seen: continue
        seen.add(feed)
        try:
            _, body=fetch(feed, 4_000_000); parsed=parse_feed(body,feed,country)
            if parsed: return parsed, final
        except Exception: continue
    # The official homepage is still the authoritative source. Crawl only its
    # own links whose path or anchor suggests the national news/press room.
    candidates=[]
    for href,_ in parser.links:
        u=urllib.parse.urljoin(final,href)
        if urllib.parse.urlparse(u).netloc != urllib.parse.urlparse(final).netloc: continue
        if re.search(r"news|actualit|press|nieuws|notizie|nachricht|comunic|medij|vijest|presse|novosti|nyheter|uutis|prensa|novità",u,re.I): candidates.append(u)
    for page_url in dict.fromkeys(candidates[:6]):
        try:
            _, body=fetch(page_url); p=Links(); p.feed(body.decode("utf-8","replace"))
            for href,_ in p.links:
                u=urllib.parse.urljoin(page_url,href)
                title=urllib.parse.urlparse(u).path.rstrip("/").split("/")[-1].replace("-"," ")
                if urllib.parse.urlparse(u).netloc==urllib.parse.urlparse(final).netloc and len(title)>16:
                    entries.append({"country":country["name"],"country_code":country["iso2"],"url":u,"title":title,"published_at":"","text":""})
        except Exception: continue
    return entries, final


def article_text(item):
    if item.get("text") and len(item["text"])>250: return item["text"][:18000]
    try:
        _, body=fetch(item["url"]); p=Links(); p.feed(body.decode("utf-8","replace"))
        return re.sub(r"\s+"," "," ".join(p.text))[:18000]
    except Exception: return item.get("text","")[:18000]


def ask_openai(text, classification=True, examples=None):
    schema={"type":"object","properties":({"english_translation":{"type":"string"},"short_english_summary":{"type":"string"}} if not classification else {
        "related":{"type":"boolean"},"primary_narrative":{"type":"string","enum":LABELS},"secondary_narratives":{"type":"array","items":{"type":"string","enum":LABELS}},"confidence":{"type":"number"},"short_rationale":{"type":"string"},"ticker_message":{"type":"string"}}),"required":(["english_translation","short_english_summary"] if not classification else ["related","primary_narrative","secondary_narratives","confidence","short_rationale","ticker_message"]),"additionalProperties":False}
    task=("Translate faithfully into English and write a neutral English summary of at most 45 words." if not classification else "Classify this official government communication using the existing narrative taxonomy. related is true only when it concerns European security, conflict, defence, sovereignty, migration, or information influence. Do not treat ordinary announcements as a narrative. A narrative label means the communication advances or describes that frame; do not infer intent. Provide a concise evidence-based rationale and a neutral ticker message of at most 18 words in English.")
    example_text=""
    if classification and examples:
        example_text="\nResearcher corrections from earlier source reviews (use as calibration examples):\n"+json.dumps(examples[-30:],ensure_ascii=False)
    req={"model":os.getenv("GOVERNMENT_MODEL","gpt-4.1-mini"),"input":[{"role":"system","content":task+"\nNarrative labels: "+", ".join(LABELS)+example_text},{"role":"user","content":text}],"text":{"format":{"type":"json_schema","name":"government_item","strict":True,"schema":schema}}}
    http=urllib.request.Request("https://api.openai.com/v1/responses",data=json.dumps(req).encode(),headers={"Authorization":"Bearer "+os.environ["OPENAI_API_KEY"],"Content-Type":"application/json"})
    with urllib.request.urlopen(http,timeout=90) as r: result=json.load(r)
    out="".join(x.get("text","") for o in result.get("output",[]) for x in o.get("content",[]) if x.get("type")=="output_text")
    return json.loads(out)


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--since",default=""); ap.add_argument("--until",default=""); ap.add_argument("--discovery-only",action="store_true"); args=ap.parse_args()
    now=dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    state=json.loads(STATE.read_text()) if STATE.exists() else {"last_successful_collection_end":None,"items":[]}
    start=date_value(args.since) or date_value(state.get("last_successful_collection_end")) or dt.datetime(2026,10,1,tzinfo=dt.timezone.utc)
    end=date_value(args.until) or now
    existing={x["id"]:x for x in state.get("items",[])}; sources_status=[]; candidates=[]
    corrections=json.loads(CORRECTIONS.read_text()) if CORRECTIONS.exists() else []
    correction_map={x["id"]:x for x in corrections if x.get("id")}
    calibration_ids={x["id"] for x in existing.values() if x.get("calibration_item")}
    calibration_complete=bool(state.get("calibration_complete")) or bool(calibration_ids and calibration_ids.issubset(correction_map))
    for ident, correction in correction_map.items():
        if ident in existing:
            existing[ident].update({"primary_narrative":correction["primary_narrative"],"secondary_narratives":correction.get("secondary_narratives",[]),"related":correction["related"],"classification_status":"human_reviewed","human_reviewed":True})
    if calibration_complete:
        candidates.extend(x for x in existing.values() if x.get("classification_status")=="awaiting_calibration")
    for source in SOURCES:
        try:
            entries, final=discover(source); sources_status.append({"country_code":source["iso2"],"country":source["name"],"official_home":final,"status":"discovered","candidate_count":len(entries)})
            for item in entries:
                pub=date_value(item.get("published_at"))
                if pub and not(start<=pub<=end): continue
                if not pub and not args.since and state.get("last_successful_collection_end"): continue
                item["published_at"]=(pub or end).isoformat(); item["id"]=hashlib.sha256(item["url"].encode()).hexdigest()[:20]
                if item["id"] not in existing: candidates.append(item)
        except Exception as e: sources_status.append({"country_code":source["iso2"],"country":source["name"],"official_home":source["url"],"status":"source_unavailable","error":type(e).__name__})
        time.sleep(.15)
    if not args.discovery_only:
        # The first tenth of a backfill is a calibration tranche. It is published
        # for researcher review; the workflow keeps subsequent items queued until
        # GOVERNMENT_CALIBRATION_READY is explicitly enabled after corrections.
        calibrating=not calibration_complete
        candidates.sort(key=lambda x: hashlib.sha256(x["id"].encode()).hexdigest())
        cap=max(1,(len(candidates)+9)//10) if calibrating and not calibration_ids else (0 if calibrating else len(candidates))
        for item in candidates[:cap]:
            text=article_text(item)
            if not text: item["classification_status"]="no_text"; existing[item["id"]]=item; continue
            translated=ask_openai(text,False); item["english_translation"]=translated["english_translation"][:18000]; item["english_summary"]=translated["short_english_summary"]
            examples=[{**correction,"title":existing[ident].get("title"),"summary":existing[ident].get("english_summary")} for ident,correction in correction_map.items() if ident in existing]
            labels=ask_openai(item["english_translation"],True,examples); item.update(labels); item["classification_status"]="provisional"; item["review_sample"]=(int(item["id"][:8],16)%100<3); item["calibration_item"]=bool(calibrating and not calibration_ids); item["source_text_chars"]=len(text); item.pop("text",None); item.pop("english_translation",None); existing[item["id"]]=item
        for item in candidates[cap:]: item["classification_status"]="awaiting_calibration"; item.pop("text",None); existing[item["id"]]=item
    calibration_ids={x["id"] for x in existing.values() if x.get("calibration_item")}
    calibration_complete=bool(state.get("calibration_complete")) or bool(calibration_ids and calibration_ids.issubset(correction_map))
    out={"as_of":end.isoformat(),"window_start":start.isoformat(),"window_end":end.isoformat(),"taxonomy_version":json.loads((ROOT/"config/narratives.json").read_text())["version"],"sources":sources_status,"items":sorted(existing.values(),key=lambda x:x.get("published_at",""),reverse=True),"review":{"routine_sample_percent":3,"calibration_tranche_percent":10,"calibration_ready":calibration_complete}}
    STATE.parent.mkdir(exist_ok=True); STATE.write_text(json.dumps({"last_successful_collection_end":end.isoformat(),"calibration_complete":calibration_complete,"items":out["items"]},ensure_ascii=False,indent=2)+"\n")
    PUBLIC.parent.mkdir(exist_ok=True)
    public={**out,"items":[{k:v for k,v in item.items() if k!="english_translation"} for item in out["items"]]}
    PUBLIC.write_text(json.dumps(public,ensure_ascii=False,indent=2)+"\n")
    REVIEW_QUEUE.parent.mkdir(exist_ok=True)
    REVIEW_QUEUE.write_text(json.dumps({"instructions":"Review every calibration_item before calibration is complete. Thereafter review the 3% routine sample. Return corrections as a JSON array with id, related, primary_narrative, secondary_narratives.","items":[{k:v for k,v in item.items() if k in {"id","country","country_code","url","title","published_at","english_summary","related","primary_narrative","secondary_narratives","short_rationale","calibration_item","review_sample"}} for item in out["items"] if item.get("calibration_item") or (item.get("review_sample") and not item.get("human_reviewed"))]},ensure_ascii=False,indent=2)+"\n")
    ok=sum(x["status"]=="discovered" for x in sources_status)
    print(json.dumps({"window_start":out["window_start"],"window_end":out["window_end"],"sources_ok":ok,"sources_unavailable":sum(x["status"]!="discovered" for x in sources_status),"new_items":len(candidates),"stored_items":len(existing),"awaiting_calibration":sum(x.get("classification_status")=="awaiting_calibration" for x in out["items"]),"review_items":sum(x.get("review_sample") is True for x in out["items"])}))
    if ok < 40: raise SystemExit("Fewer than 40 official news sources were reachable; collection cursor was not advanced safely.")

if __name__ == "__main__": main()
