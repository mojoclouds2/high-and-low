# High & Low: Dev Handoff

South Jersey dispensary price-comparison site. This package contains the new design components, a statewide NJ menu-platform scan, the crawler that produced it, and a spec for merging it into the existing site.

**Start here:** `docs/handoff-spec.md`

```
design/    Static mockup (open design/index.html): desktop results, phone results, product detail. One shared styles.css.
data/      NJ dispensary platform scan (xlsx, json, short summary)
scanner/   crawl.py + stores.csv + results; see scanner/README.md
docs/      handoff-spec.md (the spec), business-notes.md (context)
```

## Quick facts
- 331 NJ locations scanned (CRC map, Oct 2026); 258 identified (78%).
- Top platforms: Dutchie 123, Dispense 55, Sweed 37. Build scrapers in that order.
- The mockup is static HTML/CSS with placeholder content; it has no behavior, search, or real data.
- Items marked NEEDS REVIEW in the spec are legal/business decisions.

## Running the scanner
Requires Python 3 and Playwright (`pip install playwright && playwright install chromium`). From `scanner/`:
```
py crawl.py discover     # rebuild stores.csv from the CRC map
py crawl.py detect       # detect menu platforms (resumable)
py crawl.py summary      # write results.csv
```
