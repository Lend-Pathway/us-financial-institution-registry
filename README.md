# US Financial Institution Registry

Every active US bank and credit union, plus the major fintechs, in one JSON
file with a canonical slug per institution. 8,629 records: 4,259 banks from the
[FDIC registry](https://banks.data.fdic.gov), 4,336 credit unions from the
[NCUA registry](https://ncua.gov/analysis/credit-union-corporate-call-report-data),
34 fintechs curated by hand. Pulled July 2026.

Financial documents write institution names however they want: "JPMORGAN CHASE
BANK NA", "Chase", "JPM". This dataset maps that free text to one stable key
per institution. Built for statement parsing, transaction enrichment, and
entity matching.

## Record

| field | type | |
|---|---|---|
| `slug` | `str` | unique key: `chase`, `navy_fcu`, `citizens_bank_ri` |
| `display_name` | `str` | the name a statement prints, not the legal name |
| `institution_type` | `bank \| credit_union \| fintech \| other` | |
| `fdic_cert` | `int?` | banks |
| `ncua_charter` | `int?` | credit unions |
| `rssd_id` | `int?` | Federal Reserve ID, banks and credit unions |
| `meta.legal_name` | `str?` | registry name, verbatim |
| `meta.website` | `str?` | |
| `meta.favicon` | `str?` | icon URL from the site, verified to return an image |
| `meta.headquarters` | `{city?, state?}` | |
| `meta.assets_usd` | `int?` | |
| `meta.deposits_usd` | `int?` | banks only |
| `meta.trade_names` | `list[str]?` | credit unions: registered DBAs |
| `meta.partner_banks` | `list[str]?` | fintechs: the chartered banks holding deposits |

[`models.py`](models.py) defines this as Pydantic models and validates the
dataset, including the type/ID rules: banks carry `fdic_cert`, credit unions
carry `ncua_charter`, fintechs are not chartered and carry no IDs.

Favicons cover about 90% of sites; the rest are dead domains, WAF blocks, or
sites with no icon. Icons move when sites redeploy, so cache them server side.
Partner banks change over time, treat them as hints.

## Slugs

Slugs are unique across the whole file. When names collide for real (there are
19 distinct banks named "Citizens Bank") the slugs carry a state suffix:
`citizens_bank_ri`, `citizens_bank_ar`. Identity lives in the regulator IDs,
never in names.

Display names come from the registry legal names by deleting boilerplate
("National Association", ", Inc."), restoring the suffix NCUA strips from
credit union names, and preferring a registered trade name where it is clearly
the brand (BECU, 3Rivers). About 80 brands that can't be derived mechanically
are hand-mapped in [`build.py`](build.py), keyed by regulator ID.

## Run

```bash
python3 build.py     # fetches FDIC + NCUA, writes financial_institutions.json
python3 favicons.py  # optional, slow: probes every website for meta.favicon
python3 models.py    # validates the dataset (needs pydantic)
```

`build.py` is stdlib only. Bump the NCUA quarter in the URL at the top when a
new cycle drops.

## Motivation

We are [Lend Pathway](https://lendpathway.com). Our parser reads bank
statements and has to attribute each account to a real institution, which
requires exactly this table. We built it, we keep it current, and there was no
reason to keep it private.

MIT license. Author: Armaan Kapoor.
