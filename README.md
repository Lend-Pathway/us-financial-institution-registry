# US Financial Institution Registry

Every active US bank and credit union, plus the major fintechs, in one JSON
file with a canonical slug per institution. 8,629 records: 4,259 banks from the
[FDIC registry](https://banks.data.fdic.gov), 4,336 credit unions from the
[NCUA registry](https://ncua.gov/analysis/credit-union-corporate-call-report-data),
34 fintechs curated by hand. Pulled July 2026.

Financial documents write institution names however they want: "JPMORGAN CHASE
BANK NA", "Chase", "JPM". This gives you one stable key per real institution to
resolve that mess against. Useful anywhere free text needs to become a known
institution: statement parsing, transaction enrichment, entity matching.

```json
{
  "slug": "chase",
  "display_name": "Chase",
  "institution_type": "bank",
  "fdic_cert": 628,
  "ncua_charter": null,
  "rssd_id": 852218,
  "meta": {
    "legal_name": "JPMorgan Chase Bank, National Association",
    "website": "www.jpmorganchase.com",
    "favicon": "https://www.jpmorganchase.com/etc.clientlibs/cws/clientlibs/clientlib-base/resources/jpmc/images/jpmc-favicon-120.png",
    "headquarters": {"city": "Columbus", "state": "OH"},
    "assets_usd": 4016571000000,
    "deposits_usd": 2787994000000
  }
}
```

`display_name` is what a statement would print; the registry legal name is kept
verbatim in `meta`. Slugs are unique across the whole file. When names collide
for real (there are 19 distinct banks named "Citizens Bank") the slugs carry a
state suffix: `citizens_bank_ri`, `citizens_bank_ar`. Identity lives in the
regulator IDs, never in names. Fintechs are not chartered, so they have no IDs;
their `meta.partner_banks` lists the banks that hold their deposits.

Most records have `meta.favicon`: the institution's own icon URL, read from its
website and verified to return an image. About 90% of sites yield one. Icons
move when sites redeploy, so cache them server side if you render these;
`python3 favicons.py` refreshes the column.

## Run

```bash
python3 build.py     # fetches FDIC + NCUA, writes financial_institutions.json
python3 favicons.py  # optional, slow: probes every website for meta.favicon
python3 models.py    # validates the dataset (needs pydantic)
```

`build.py` is stdlib only. Bump the NCUA quarter in the URL at the top when a
new cycle drops.

## Motivation

We are [Lend Pathway](https://lendpathway.com). Our parser reads hundreds of
thousands of bank statements, and every transaction needs to be attributed to a
real institution. Bank names in the wild were chaos; canonical slugs fixed it.
Anyone parsing financial documents hits the same wall, so here it is.

MIT license. Author: Armaan Kapoor.
