"""Resolve an official full speech behind one China archive attachment notice."""
import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path

from collect_government_news import fetch

RECORD_ID = "0d3da572f379627b0365"
ARCHIVE = "https://english.www.gov.cn/news/202610/18/content_WS6ad4d9c8c6d00ca5f9a0dc44.html"
FULL_SPEECH = "https://www.fmprc.gov.cn/mfa_eng/xw/zyjh/202610/t20261018_12042328.html"
STATE = Path("data/government_state.json")


class BodyText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_body = False
        self.skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "body":
            self.in_body = True
        elif self.in_body and tag in {"script", "style", "nav", "footer"}:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag == "body":
            self.in_body = False
        elif tag in {"script", "style", "nav", "footer"}:
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if self.in_body and not self.skip and data.strip():
            self.parts.append(data.strip())


def full_speech_text():
    _, body = fetch(FULL_SPEECH, timeout=25)
    parser = BodyText()
    parser.feed(body.decode("utf-8", "replace"))
    page = re.sub(r"\s+", " ", " ".join(parser.parts))
    start = page.find("Beijing, October 17, 2026")
    end = page.find("Thank you.", start)
    if start < 0 or end < 0:
        raise RuntimeError("Official MFA speech boundaries could not be verified")
    speech = page[start:end + len("Thank you.")].strip()
    required = ("World Conference on Traditional Medicine",
                "artificial intelligence and modern biomedicine",
                "infectious diseases")
    if len(speech) < 3500 or any(phrase not in speech for phrase in required):
        raise RuntimeError("Official MFA full speech failed source identity/content checks")
    return speech


def repair_state(path=STATE):
    state = json.loads(path.read_text())
    items = [item for item in state.get("items", []) if item.get("id") == RECORD_ID]
    if len(items) != 1 or items[0].get("url") != ARCHIVE:
        raise RuntimeError("Expected archive record is missing or source identity changed")
    item = items[0]
    speech = full_speech_text()
    digest = hashlib.sha256(speech.encode("utf-8")).hexdigest()
    item.update(full_source_url=FULL_SPEECH, source_text_chars=len(speech),
                translated_text_chars=len(speech), source_text_sha256=digest)
    # The private checkpoint retains the official full source; the public
    # export strips the text field and keeps only provenance and character count.
    item["text"] = speech
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    print("Repaired official full speech for " + RECORD_ID +
          ": " + str(len(speech)) + " characters; SHA-256 " + digest)


if __name__ == "__main__":
    repair_state()
