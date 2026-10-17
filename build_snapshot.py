"""Rebuild out/products.json + out/index.html offline from the saved store data in data/ (no scraping).
Useful for tweaking the page design: edit template.html, then run  python build_snapshot.py"""
import json
from datetime import datetime, timezone
from pathlib import Path

import normalize as N
from scrape import sage_row, dutchie_rows, qr_row, dispense_row, build_html, OUT, DISPENSE

D = Path(__file__).parent / "data"
ACTIVE = N.active_stores()
rows = [sage_row(r) for r in json.load(open(D / "sage_detail.json"))] if "sage" in ACTIVE else []
brand_extra = {}
for store in [s for s in ("nar", "gynsyng", "brotherlybud", "enlighten") if s in ACTIVE]:
    for r in json.load(open(D / f"{store}_detail.json")):
        rows += dutchie_rows(store, {"medPrices": [], "medSpecial": [], **r})
        if r.get("brandDesc") and r.get("brand"):
            brand_extra.setdefault(r["brand"].strip().lower(), {"n": r["brand"], "t": r["brandDesc"].strip(), "s": store})
if "qualityroots" in ACTIVE:
    rows += [qr_row(r) for r in json.load(open(D / "qualityroots_detail.json"))]
for store in [s for s in ("daylite", "nirvana") if s in ACTIVE]:
    rows += [dispense_row(store, DISPENSE[store], r) for r in json.load(open(D / f"{store}_detail.json"))]

rows = [r for r in rows if N.keep(r)]
# show when the saved data was captured, not when the page was rebuilt
cap = D / "captured_at.txt"
now = cap.read_text().strip() if cap.exists() else datetime.now(timezone.utc).isoformat(timespec="seconds")
status = {s: {"ok": True, "count": sum(1 for x in rows if x["store"] == s), "last_ok": now} for s in ACTIVE}
brands = json.load(open(D / "brands.json"))
for k, v in brand_extra.items():
    if k not in brands or len(v["t"]) > len(brands[k]["t"]):
        brands[k] = v
payload = {"updated": now, "stores": ACTIVE, "status": status, "brands": brands, "products": rows}
OUT.mkdir(exist_ok=True)
(OUT / "products.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
build_html(payload)
print(status)
