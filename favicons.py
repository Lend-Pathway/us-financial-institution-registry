"""Enriches financial_institutions.json with a verified favicon URL per institution.

    python3 favicons.py

Fetches each institution's website, reads its declared icons (preferring
apple-touch-icon over favicon.ico), and stores the first URL that actually
returns an image as meta.favicon. Slow (~30 min for 8k sites) and inherently
best-effort: sites block, rot, and move. build.py does not need this; run it
after a rebuild if you want the favicon column refreshed.
"""

import json
import re
import ssl
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

DATASET = Path(__file__).parent / "financial_institutions.json"
TIMEOUT = 12
CTX = ssl.create_default_context()
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
IMAGE_MAGIC = (b"\x89PNG", b"\x00\x00\x01\x00", b"GIF8", b"\xff\xd8\xff", b"<svg", b"<?xml", b"RIFF", b"BM")
# Website-builder default icons: the platform's logo, not the institution's.
DEFAULT_ICONS = re.compile(r"parastorage\.com/client/pfavico|logo-default|universal/default-favicon")


class IconParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.icons = []

    def handle_starttag(self, tag, attrs):
        if tag != "link":
            return
        a = dict(attrs)
        rel = (a.get("rel") or "").lower()
        if not a.get("href") or "icon" not in rel:
            return
        if "apple-touch" in rel:
            priority = 0
        elif "mask" in rel:
            priority = 3
        else:
            m = re.search(r"(\d+)", a.get("sizes") or "")
            priority = 1 if m and int(m.group(1)) >= 64 else 2
        self.icons.append((priority, a["href"]))


def fetch(url, referer=None, limit=512_000):
    headers = dict(HEADERS, Referer=referer) if referer else HEADERS
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=TIMEOUT, context=CTX) as response:
        return response.geturl(), response.headers.get("Content-Type", ""), response.read(limit)


def is_image(content_type, body):
    if not body:
        return False
    if content_type.split(";")[0].strip().lower().startswith("image/"):
        return True
    return body[:16].lstrip().lower().startswith(IMAGE_MAGIC) or body[:4] in IMAGE_MAGIC


def probe(site):
    host = re.sub(r"(?i)^https?://", "", site).split("/")[0]
    hosts = [host, host[4:] if host.startswith("www.") else f"www.{host}"]

    page_url, candidates = None, []
    for origin in (f"{scheme}://{h}/" for h in hosts for scheme in ("https", "http")):
        try:
            page_url, _, html = fetch(origin)
        except Exception:
            continue
        parser = IconParser()
        try:
            parser.feed(html.decode("utf-8", "replace"))
        except Exception:
            pass
        candidates = [urljoin(page_url, href) for _, href in sorted(parser.icons)]
        break
    # Conventional paths; sites serve these undeclared, and some that block
    # page loads still serve the icon itself.
    base = page_url or f"https://{host}/"
    candidates += [urljoin(base, "/apple-touch-icon.png"), urljoin(base, "/favicon.ico")]

    seen = set()
    for candidate in candidates:
        if candidate in seen or candidate.startswith("data:") or DEFAULT_ICONS.search(candidate):
            continue
        seen.add(candidate)
        try:
            url, content_type, body = fetch(candidate, referer=page_url)
            if is_image(content_type, body):
                return url
        except Exception:
            continue
    return None


def main():
    records = json.loads(DATASET.read_text())
    todo = [r for r in records if r["meta"].get("website")]
    print(f"probing {len(todo)} sites")

    with ThreadPoolExecutor(max_workers=48) as pool:
        results = pool.map(lambda r: probe(r["meta"]["website"]), todo)
        for i, (record, favicon) in enumerate(zip(todo, results)):
            # rebuild meta so favicon sits next to website
            meta = {}
            for key, value in record["meta"].items():
                meta[key] = value
                if key == "website" and favicon:
                    meta["favicon"] = favicon
            record["meta"] = meta
            if (i + 1) % 500 == 0:
                print(f"{i + 1}/{len(todo)}", flush=True)

    DATASET.write_text(json.dumps(records, indent=1, ensure_ascii=False) + "\n")
    found = sum(1 for r in records if r["meta"].get("favicon"))
    print(f"favicons for {found}/{len(todo)} sites with a website")


if __name__ == "__main__":
    main()
