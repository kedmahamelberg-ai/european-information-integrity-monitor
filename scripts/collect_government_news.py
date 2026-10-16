"""Collect public national-government news, translate it, and classify narratives."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    with urllib.request.urlopen(req, timeout=8) as r:
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


def publication_date(body, url):
    page = body.decode("utf-8", "replace")
    patterns = [
        r'<meta[^>]+(?:property|name)=["\'](?:article:published_time|datePublished|pubdate|date)["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:article:published_time|datePublished|pubdate|date)["\']',
        r'<time[^>]+datetime=["\']([^"\']+)',
        r'["\']datePublished["\']\s*:\s*["\']([^"\']+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, page, re.I)
        if match:
            parsed = date_value(match.group(1))
            if parsed: return parsed
    match = re.search(r'/((?:20\d{2})/(?:0?[1-9]|1[0-2])/(?:0?[1-9]|[12]\d|3[01]))(?:/|$)', urllib.parse.urlparse(url).path)
    if match: return date_value(match.group(1).replace('/', '-'))
    return None


def discover(country):
    # Fetch only the registered executive news or press section. Never follow
    # generic homepage feeds or discover an unrelated section automatically.
    final, page = fetch(country["url"])
    base = urllib.parse.urlparse(final)
    body = page.decode("utf-8", "replace")
    links = []
    seen = set()
    for match in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', body, re.I | re.S):
        link = urllib.parse.urljoin(final, html.unescape(match.group(1)))
        parsed = urllib.parse.urlparse(link)
        title = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', match.group(2)))).strip()
        if parsed.netloc.lower() != base.netloc.lower() or len(title) < 18 or len(title) > 240: continue
        if parsed.scheme not in ('http', 'https') or re.search(r'\.(?:pdf|jpg|jpeg|png|webp|svg|zip)$', parsed.path, re.I): continue
        clean = urllib.parse.urlunparse(parsed._replace(fragment=''))
        if clean == final or clean in seen: continue
        if parsed.path.rstrip('/') in ('', '/', base.path.rstrip('/')): continue
        seen.add(clean)
        links.append((clean, title))
        if len(links) >= 32: break
    entries = []
    for link, title in links:
        try:
            _, article = fetch(link)
            published = publication_date(article, link)
            if not published: continue
            p = Links(); p.feed(article.decode('utf-8', 'replace'))
            entries.append({'country': country['name'], 'country_code': country['iso2'], 'url': link, 'title': title, 'published_at': published.isoformat(), 'text': re.sub(r'\s+', ' ', ' '.join(p.text))[:18000]})
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
    last_problem="empty response"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(http,timeout=90) as r: result=json.load(r)
            out=result.get("output_text") or "".join(x.get("text","") for o in result.get("output",[]) for x in o.get("content",[]) if x.get("type")=="output_text")
            if out.strip():
                try: return json.loads(out)
                except json.JSONDecodeError as exc: last_problem=f"invalid JSON at character {exc.pos}"
            else: last_problem=f"empty response (status={result.get('status')}, incomplete={result.get('incomplete_details')}, error={result.get('error')})"
        except (urllib.error.URLError,TimeoutError) as exc:
            last_problem=f"{type(exc).__name__}: {exc}"
        if attempt<2: time.sleep(2**attempt)
    raise RuntimeError(f"OpenAI response could not be parsed after 3 attempts: {last_problem}")
    out=result.get("output_text") or "".join(x.get("text","") for o in result.get("output",[]) for x in o.get("content",[]) if x.get("type")=="output_text")
    return json.loads(out)


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--since",default=""); ap.add_argument("--until",default=""); ap.add_argument("--discovery-only",action="store_true"); args=ap.parse_args()
    now=dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    state=json.loads(STATE.read_text()) if STATE.exists() else {"last_successful_collection_end":None,"items":[]}
    start=date_value(args.since) or date_value(state.get("last_successful_collection_end")) or dt.datetime(2026,10,1,tzinfo=dt.timezone.utc)
    end=date_value(args.until) or now
    if args.until and re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.until):
        end=end+dt.timedelta(days=1)-dt.timedelta(microseconds=1)
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
    # Discover the official sources concurrently and log each completion.
    # With bounded request timeouts, slow sites cannot stall the whole batch.
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures={pool.submit(discover,source):source for source in SOURCES if source.get("verification_status") == "verified"}
        for future in as_completed(futures):
            source=futures[future]
            try:
                entries, final=future.result()
                sources_status.append({"country_code":source["iso2"],"country":source["name"],"official_home":final,"status":"discovered","candidate_count":len(entries)})
                for item in entries:
                    pub=date_value(item.get("published_at"))
                    if pub and not(start<=pub<=end): continue
                    if not pub: continue
                    item["published_at"]=(pub or end).isoformat(); item["id"]=hashlib.sha256(item["url"].encode()).hexdigest()[:20]
                    if item["id"] not in existing: candidates.append(item)
                print(f"Discovered {source['name']}: {len(entries)} candidate links",flush=True)
            except Exception as e:
                sources_status.append({"country_code":source["iso2"],"country":source["name"],"official_home":source["url"],"status":"source_unavailable","error":type(e).__name__})
                print(f"Unavailable {source['name']}: {type(e).__name__}",flush=True)
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
            labels=ask_openai(item["english_translation"],True,examples); item.update(labels); item["classification_status"]="provisional"; item["review_sample"]=(int(item["id"][:8],16)%100<3); item["calibration_item"]=bool(calibrating and not calibration_ids); item["source_text_chars"]=len(text); item.pop("text",None); item.pop("english_translation",None); existing[item["id"]]=item; STATE.parent.mkdir(exist_ok=True); STATE.write_text(json.dumps({"last_successful_collection_end":state.get("last_successful_collection_end"),"calibration_complete":calibration_complete,"items":list(existing.values())},ensure_ascii=False,indent=2)+"\n")
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
    if not ok: raise SystemExit("No verified official news sections were reachable.")

if __name__ == "__main__": main()
