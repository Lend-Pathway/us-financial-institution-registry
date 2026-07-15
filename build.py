"""Builds financial_institutions.json: every active US bank (FDIC registry),
every active credit union (NCUA registry), and the curated fintech list below.

    python3 build.py
"""

import csv
import io
import json
import re
import time
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

FDIC_URL = (
    "https://api.fdic.gov/banks/institutions"
    "?filters=ACTIVE:1"
    "&fields=NAME,CERT,FED_RSSD,CITY,STALP,WEBADDR,ASSET,DEP"
    "&limit=10000&format=json"
)
# Bump the quarter when a new NCUA cycle drops.
NCUA_URL = "https://ncua.gov/files/publications/analysis/call-report-data-2026-03.zip"

OUT = Path(__file__).parent / "financial_institutions.json"

# Brands that can't be derived from the legal name. FDIC cert -> brand.
BANK_BRANDS = {
    628: "Chase",
    3510: "Bank of America",
    7213: "Citibank",
    3511: "Wells Fargo",
    33124: "Goldman Sachs Bank",
    6548: "U.S. Bank",
    4297: "Capital One",
    6384: "PNC Bank",
    9846: "Truist",
    639: "BNY Mellon",
    14: "State Street Bank",
    18409: "TD Bank",
    6672: "Fifth Third Bank",
    6560: "Huntington Bank",
    16571: "BMO",
    57450: "Charles Schwab Bank",
    11063: "First Citizens Bank",
    57957: "Citizens Bank",
    27471: "American Express",
    588: "M&T Bank",  # Manufacturers and Traders Trust Company
    17534: "KeyBank",
    57803: "Ally Bank",
    913: "Northern Trust",
    57890: "HSBC",
    12368: "Regions Bank",
    32188: "USAA",
    29950: "Santander",
    2270: "Zions Bank",
    57203: "Barclays",
    623: "Deutsche Bank",
    9396: "Valley Bank",
    34968: "Banco Popular",
    4214: "BOK Financial",
    5452: "FNBO",  # First National Bank of Omaha
    9712: "Rockland Trust",
    17838: "WSFS Bank",  # Wilmington Savings Fund Society
    12633: "Central Bank",  # The Central Trust Bank
    58665: "Live Oak Bank",
    30012: "Third Federal",
    # Fintech partner banks, spelled exactly as they appear on statements.
    35444: "The Bancorp Bank",
    22653: "Green Dot Bank",  # legal: Green Dot Bank DBA Bonneville Bank
    9423: "Choice Bank",  # Choice Financial Group
    59177: "Square",
    # Stylized casing the title-caser can't infer.
    11763: "VisionBank of Iowa",
    13600: "PointWest Bank",
    16704: "BankWest",
    18063: "CoreBank",
    18618: "SMBC MANUBANK",
    23498: "TBK Bank",
    29672: "cfsbank",
    34023: "TNBank",
    5335: "WoodTrust Bank",
    9875: "Bank360",
    35029: "AB&T",
    4235: "YNB",
    17580: "FNBT Bank",
    17011: "FNB South",
}

# Same, NCUA charter -> brand.
CU_BRANDS = {
    5536: "Navy Federal Credit Union",
    66310: "State Employees' Credit Union",
    24212: "SchoolsFirst Federal Credit Union",
    62604: "BECU",  # Boeing Employees Credit Union
    227: "PenFed Credit Union",
    # Their registered trade names are division or product brands, not the institution.
    67297: "Space Coast Credit Union",
    23279: "MSU Federal Credit Union",
    24984: "Hudson Valley Credit Union",
    68278: "Gesa Credit Union",
    4735: "FourLeaf Federal Credit Union",
    68187: "BCU",  # Baxter Credit Union
    61004: "SDCCU",  # San Diego County Credit Union
    61650: "Golden 1 Credit Union",
    24563: "ESL Federal Credit Union",
    60269: "GreenState Credit Union",
    # Cut off by the NCUA 35-char name field, restored by hand.
    67290: "Community First Credit Union of Florida",
    61160: "Members First Credit Union of Florida",
    68180: "BNSF Railway Credit Union",
    68616: "Zing Credit Union",  # formerly Denver Community CU
    66787: "MECU of Baltimore",
    66330: "SECU of Maryland",
}

# Neobanks. Not chartered, so no regulator IDs; deposits sit at partner banks.
FINTECHS = [
    {"name": "Chime", "legal": "Chime Financial, Inc.", "site": "www.chime.com", "city": "San Francisco", "state": "CA", "partners": ["The Bancorp Bank", "Stride Bank"]},
    {"name": "Mercury", "legal": "Mercury Technologies, Inc.", "site": "www.mercury.com", "city": "San Francisco", "state": "CA", "partners": ["Choice Bank", "Column", "Evolve Bank & Trust"]},
    {"name": "Novo", "legal": "Novo Platform, Inc.", "site": "www.novo.co", "city": "Miami", "state": "FL", "partners": ["Middlesex Federal Savings"]},
    {"name": "Bluevine", "legal": "Bluevine Inc.", "site": "www.bluevine.com", "city": "Jersey City", "state": "NJ", "partners": ["Coastal Community Bank"]},
    {"name": "Relay", "legal": "Relay Financial Technologies Inc.", "site": "www.relayfi.com", "city": "Toronto", "state": "ON", "partners": ["Thread Bank"]},
    {"name": "Found", "site": "www.found.com", "city": "San Francisco", "state": "CA", "partners": ["Piermont Bank"]},
    {"name": "Lili", "legal": "Lili App Inc.", "site": "www.lili.co", "city": "New York", "state": "NY", "partners": ["Choice Bank"]},
    {"name": "NorthOne", "legal": "NorthOne, Inc.", "site": "www.northone.com", "city": "New York", "state": "NY", "partners": ["The Bancorp Bank"]},
    {"name": "Rho", "legal": "Rho Technologies, Inc.", "site": "www.rho.co", "city": "New York", "state": "NY", "partners": ["Webster Bank"]},
    {"name": "Brex", "legal": "Brex Inc.", "site": "www.brex.com", "city": "San Francisco", "state": "CA"},
    {"name": "Ramp", "legal": "Ramp Business Corporation", "site": "www.ramp.com", "city": "New York", "state": "NY"},
    {"name": "Wise", "legal": "Wise US Inc.", "site": "www.wise.com", "city": "New York", "state": "NY", "partners": ["Community Federal Savings Bank"]},
    {"name": "Payoneer", "legal": "Payoneer Inc.", "site": "www.payoneer.com", "city": "New York", "state": "NY", "partners": ["First Century Bank"]},
    {"name": "PayPal", "legal": "PayPal, Inc.", "site": "www.paypal.com", "city": "San Jose", "state": "CA"},
    {"name": "Venmo", "legal": "PayPal, Inc. (Venmo)", "site": "www.venmo.com", "city": "New York", "state": "NY", "partners": ["The Bancorp Bank"]},
    {"name": "Cash App", "legal": "Block, Inc. (Cash App)", "site": "www.cash.app", "city": "San Francisco", "state": "CA", "partners": ["Sutton Bank"]},
    {"name": "QuickBooks Checking", "legal": "Intuit Inc. (QuickBooks Checking)", "site": "quickbooks.intuit.com", "city": "Mountain View", "state": "CA", "partners": ["Green Dot Bank"]},
    {"name": "Shopify Balance", "legal": "Shopify Inc. (Shopify Balance)", "site": "www.shopify.com", "city": "Ottawa", "state": "ON", "partners": ["Evolve Bank & Trust"]},
    {"name": "Current", "legal": "Finco Services, Inc.", "site": "www.current.com", "city": "New York", "state": "NY", "partners": ["Choice Bank"]},
    {"name": "Dave", "legal": "Dave Inc.", "site": "www.dave.com", "city": "Los Angeles", "state": "CA", "partners": ["Evolve Bank & Trust"]},
    {"name": "MoneyLion", "legal": "MoneyLion Inc.", "site": "www.moneylion.com", "city": "New York", "state": "NY", "partners": ["Pathward"]},
    {"name": "Albert", "legal": "Albert Corporation", "site": "www.albert.com", "city": "Culver City", "state": "CA", "partners": ["Sutton Bank"]},
    {"name": "One", "legal": "One Finance, Inc.", "site": "www.one.app", "city": "New York", "state": "NY", "partners": ["Coastal Community Bank"]},
    {"name": "GO2bank", "legal": "Green Dot Corporation (GO2bank)", "site": "www.go2bank.com", "city": "Austin", "state": "TX", "partners": ["Green Dot Bank"]},
    {"name": "Netspend", "legal": "Netspend Corporation", "site": "www.netspend.com", "city": "Austin", "state": "TX", "partners": ["Pathward"]},
    {"name": "Baselane", "legal": "Baselane, Inc.", "site": "www.baselane.com", "city": "New York", "state": "NY", "partners": ["Thread Bank"]},
    {"name": "Revolut", "legal": "Revolut Technologies Inc.", "site": "www.revolut.com", "city": "New York", "state": "NY"},
    {"name": "Airwallex", "legal": "Airwallex US, LLC", "site": "www.airwallex.com", "city": "San Francisco", "state": "CA"},
    {"name": "Stripe", "legal": "Stripe, Inc.", "site": "www.stripe.com", "city": "South San Francisco", "state": "CA", "partners": ["Evolve Bank & Trust", "Fifth Third Bank"]},
    {"name": "Wave", "legal": "Wave Financial Inc. (Wave Money)", "site": "www.waveapps.com", "city": "Toronto", "state": "ON", "partners": ["Community Federal Savings Bank"]},
    {"name": "Slash", "site": "www.slash.com", "city": "San Francisco", "state": "CA"},
    {"name": "Meow", "site": "www.meow.com", "city": "New York", "state": "NY", "partners": ["Grasshopper Bank"]},
    {"name": "Wealthfront", "legal": "Wealthfront Corporation", "site": "www.wealthfront.com", "city": "Palo Alto", "state": "CA", "partners": ["Green Dot Bank"]},
    {"name": "Credit Karma Money", "legal": "Intuit Inc. (Credit Karma Money)", "site": "www.creditkarma.com", "city": "Oakland", "state": "CA", "partners": ["MVB Bank"]},
]

LEGAL_SUFFIXES = [
    r",?\s+a national banking association$",
    r",?\s+national association$",
    r",\s*n\.?\s?a\.?$",
    r"\s+n\.a\.$",
    r",?\s+s\.?s\.?b\.?$",
    r",?\s+f\.?s\.?b\.?$",
    r",?\s+(inc\.?|incorporated|ltd\.?|l\.?l\.?c\.?|corp\.)$",
]

LOWER_WORDS = {"of", "and", "the", "in", "on", "at", "for", "de", "la", "del", "y"}
KEEP_UPPER = {"USA", "GTE", "IBM", "TVA", "AFL", "CIO", "DOE", "FAA", "EPA", "IRS", "ATT", "UPS"}


def collapse_ws(s):
    return re.sub(r"\s+", " ", s or "").strip()


def clean_city(s):
    city = collapse_ws(s)
    if city.isupper() or city.islower():
        city = city.title()
    return re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), city)  # Mclean -> McLean


def titlecase_word(word, first):
    letters = re.sub(r"[^A-Za-z]", "", word)
    if not letters:
        return word
    if re.fullmatch(r"\d+(ST|ND|RD|TH)", word):
        return word.lower()
    if word.lower() in LOWER_WORDS and not first:
        return word.lower()
    if letters in {"FE", "EL"}:  # Santa Fe, El Paso
        return word[0].upper() + word[1:].lower()
    if not re.search(r"[AEIOUY]", letters) or len(letters) <= 2 or letters in KEEP_UPPER:
        return word
    cased = word[0].upper() + word[1:].lower()
    if re.match(r"Mc[a-z]{2,}", cased):
        cased = "Mc" + cased[2].upper() + cased[3:]
    return cased


def smart_titlecase(name):
    out = []
    for i, word in enumerate(name.split(" ")):
        parts = re.split(r"([-/])", word)
        out.append("".join(p if p in "-/" else titlecase_word(p, first=(i == 0)) for p in parts))
    return " ".join(out)


def bank_display_name(legal):
    name = collapse_ws(legal)
    dba = re.split(r"\s+d/b/a\s+", name, flags=re.I)
    if len(dba) == 2:
        name = collapse_ws(dba[1])
    if name.isupper():
        name = smart_titlecase(name)
    changed = True
    while changed:
        changed = False
        for pattern in LEGAL_SUFFIXES:
            stripped = re.sub(pattern, "", name, flags=re.I)
            if stripped != name:
                name, changed = stripped.strip(), True
    name = re.sub(r",\s*The$", "", name)  # FDIC writes "Business Bank, The"
    name = re.sub(r",\s*A$", "", name)
    name = name.rstrip(" ,")
    stripped = re.sub(r"^The\s+", "", name)
    if len(stripped.split()) >= 2:  # "The Bank" is a real bank; leave it whole
        name = stripped
    return collapse_ws(name)


TRADE_NAME_BLOCKLIST = {"none", "n/a", "na", "kasasa", "easy banking"}
TRADE_NAME_JUNK = re.compile(r"\b(branch|division|mortgage|marketing|insurance|realty|title|llc)\b", re.I)


def pick_trade_name(trade_names, charter_name):
    # The NCUA trade-names file mixes real brands with branch names, division
    # DBAs, and product names. Score candidates; only a clear win displaces the
    # legal name.
    tokens = {t.lower() for t in re.findall(r"[A-Za-z0-9]{4,}", charter_name)}
    best, best_score = None, 0
    seen = set()
    for candidate in trade_names:
        candidate = collapse_ws(candidate)
        key = candidate.lower()
        if not candidate or key in seen:
            continue
        seen.add(key)
        if key in TRADE_NAME_BLOCKLIST or len(candidate) < 3 or len(candidate) >= 32:
            continue
        if TRADE_NAME_JUNK.search(candidate) or re.search(r"www\.|\.(com|org|net)\b", key):
            continue
        score = 1
        if any(token in key for token in tokens):
            score += 3
        if re.search(r"(credit union|f\.?c\.?u\.?|\bcu)$", key):
            score += 2
        if not candidate.isupper():
            score += 1
        if score > best_score:
            best, best_score = candidate, score
    if best is None:
        return None
    if best.isupper() and not (len(best) <= 6 or re.search(r"F?CU$", best)):
        best = smart_titlecase(best)
    return best


def cu_legal_name(raw, cu_type):
    # NCUA stores names without their suffix ("BROADVIEW") in a 35-char field,
    # so some arrive cut mid-word: ", A Federal Credit Union" -> ", A",
    # "CREDIT UNION" -> "CREDIT UN.", "CREDIT ASSOCIATION" -> "CREDIT AS".
    name = collapse_ws(raw)
    name = re.sub(r",\s*inc?\.?$", "", name, flags=re.I)
    name = re.sub(r"\s+(inc\.?|incorporat(ed)?)$", "", name, flags=re.I)
    name = re.sub(r",\s*A$", "", name)
    m = re.search(r"\s(CRED[A-Z]*\.?( [A-Z]{1,10}\.?)?)$", name.upper())
    if m:
        fragment = m.group(1).replace(".", "")
        if fragment != "CREDIT UNION" and "CREDIT UNION".startswith(fragment):
            name = name[: m.start()]
        elif fragment not in ("CREDIT", "CREDIT ASSOCIATION") and "CREDIT ASSOCIATION".startswith(fragment):
            name = name[: m.start()] + " CREDIT ASSOCIATION"
    if name.isupper():
        name = smart_titlecase(name)
    upper = name.upper()
    if ("CREDIT UNION" in upper or "CREDIT ASSOCIATION" in upper
            or re.search(r"F\.?C\.?U\.?$", upper) or re.search(r"\bCU\b", upper)):
        return collapse_ws(name)
    suffix = "Federal Credit Union" if cu_type == 1 else "Credit Union"
    return collapse_ws(f"{name} {suffix}")


def slugify(name):
    s = name.lower().replace("&", " and ")
    s = re.sub(r"[’'.,]", "", s)  # registry names use both apostrophes
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def website(url):
    # Registry website fields contain typos and truncations ("http://https://x.com",
    # "www.bank.", "…creditunion.o"). Anything without a sane host becomes null.
    u = re.split(r"[;,\s]", collapse_ws(url or ""))[0]
    u = re.sub(r"(?i)^(https?://)+(?=https?://)", "", u)
    m = re.match(r"(?i)^(https?://)?([^/]+?)\.?(/.*)?$", u.rstrip("/"))
    if not m or not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}", m.group(2).lower()):
        return None
    return f"{(m.group(1) or '').lower()}{m.group(2).lower()}{m.group(3) or ''}"


def record(slug, display, kind, fdic=None, ncua=None, rssd=None, meta=None):
    return {
        "slug": slug,
        "display_name": display,
        "institution_type": kind,
        "fdic_cert": fdic,
        "ncua_charter": ncua,
        "rssd_id": rssd,
        "meta": meta or {},
    }


def build_banks(fdic):
    assert fdic["meta"]["total"] == len(fdic["data"]), "FDIC pull truncated; raise the limit"
    records = []
    for row in (r["data"] for r in fdic["data"]):
        cert = int(row["CERT"])
        legal = collapse_ws(row["NAME"])
        display = BANK_BRANDS.get(cert) or bank_display_name(legal)
        rssd = str(row.get("FED_RSSD", "")).strip()
        meta = {
            "legal_name": legal,
            "website": website(row.get("WEBADDR")),
            "headquarters": {"city": clean_city(row.get("CITY")) or None,
                             "state": collapse_ws(row.get("STALP")) or None},
            # FDIC reports money in $ thousands.
            "assets_usd": row["ASSET"] * 1000 if row.get("ASSET") is not None else None,
            "deposits_usd": row["DEP"] * 1000 if row.get("DEP") is not None else None,
        }
        records.append(record(slugify(display), display, "bank", fdic=cert,
                              rssd=int(rssd) if rssd.isdigit() and int(rssd) else None, meta=meta))
    return records


def build_credit_unions(ncua_zip):
    def rows(filename):
        return csv.DictReader(io.TextIOWrapper(ncua_zip.open(filename), encoding="latin-1"))

    assets = {}
    for row in rows("FS220.txt"):
        try:
            assets[row["CU_NUMBER"]] = int(float(row["ACCT_010"]))
        except (ValueError, KeyError):
            pass
    websites = {row["CU_NUMBER"]: w for row in rows("FS220D.txt") if (w := collapse_ws(row.get("Acct_891")))}
    trade_names = defaultdict(list)
    for row in rows("TradeNames.txt"):
        if (t := collapse_ws(row.get("TradeName"))) and t.lower() not in ("none", "n/a", "na"):
            trade_names[row["CU_NUMBER"]].append(t)

    records = []
    for row in rows("FOICU.txt"):
        cu = row["CU_NUMBER"]
        charter = int(cu)
        legal = cu_legal_name(row["CU_NAME"], int(row["CU_TYPE"]))
        display = CU_BRANDS.get(charter) or pick_trade_name(trade_names[cu], row["CU_NAME"]) or legal
        meta = {
            "legal_name": legal,
            "website": website(websites.get(cu)),
            "headquarters": {"city": clean_city(row.get("CITY")) or None,
                             "state": collapse_ws(row.get("STATE")) or None},
            "assets_usd": assets.get(cu),  # NCUA reports plain dollars
        }
        if trade_names[cu]:
            meta["trade_names"] = trade_names[cu]
        slug = slugify(display)
        slug = re.sub(r"_federal_credit_union$", "_fcu", slug)
        slug = re.sub(r"_credit_union$", "_cu", slug)
        records.append(record(slug, display, "credit_union", ncua=charter,
                              rssd=int(row["RSSD"]) if row["RSSD"].strip().isdigit() else None, meta=meta))
    return records


def build_fintechs():
    records = []
    for f in FINTECHS:
        meta = {}
        if "legal" in f:
            meta["legal_name"] = f["legal"]
        meta["website"] = f["site"]
        meta["headquarters"] = {"city": f["city"], "state": f["state"]}
        if "partners" in f:
            meta["partner_banks"] = f["partners"]
        records.append(record(slugify(f["name"]), f["name"], "fintech", meta=meta))
    return records


def dedupe_slugs(records):
    # Colliding slugs get a state suffix, then city, then regulator ID.
    suffixes = [
        lambda r: (r["meta"]["headquarters"]["state"] or "xx").lower(),
        lambda r: slugify(r["meta"]["headquarters"]["city"] or "x"),
        lambda r: str(r["fdic_cert"] or r["ncua_charter"] or r["rssd_id"]),
    ]
    for suffix in suffixes:
        groups = defaultdict(list)
        for r in records:
            groups[r["slug"]].append(r)
        for group in groups.values():
            if len(group) > 1:
                for r in group:
                    r["slug"] = f"{r['slug']}_{suffix(r)}"


def validate(records):
    slugs = set()
    for r in records:
        assert re.fullmatch(r"[a-z0-9_]+", r["slug"]), r
        assert r["slug"] not in slugs, f"duplicate slug {r['slug']}"
        slugs.add(r["slug"])
        assert r["display_name"]
        if r["institution_type"] in ("bank", "credit_union"):
            assert r["fdic_cert"] or r["ncua_charter"], f"no identity: {r}"


def get(url, attempts=3):
    request = urllib.request.Request(url, headers={"User-Agent": "us-financial-institution-registry"})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                return response.read()
        except OSError:
            if attempt == attempts - 1:
                raise
            time.sleep(2 ** (attempt + 1))


def main():
    fdic = json.loads(get(FDIC_URL))
    ncua_zip = zipfile.ZipFile(io.BytesIO(get(NCUA_URL)))

    records = build_banks(fdic) + build_credit_unions(ncua_zip) + build_fintechs()
    order = {"bank": 0, "credit_union": 1, "fintech": 2}
    records.sort(key=lambda r: (order[r["institution_type"]], -(r["meta"].get("assets_usd") or 0)))
    dedupe_slugs(records)
    validate(records)

    OUT.write_text(json.dumps(records, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {len(records)} records to {OUT}")


if __name__ == "__main__":
    main()
