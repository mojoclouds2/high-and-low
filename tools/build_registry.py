"""Bootstrap stores.json (the store registry) from the NJ platform scan plus the original eight stores' settings.
Run once:  python tools/build_registry.py            (refuses to overwrite an existing stores.json unless --force)
After that, edit stores.json by hand or let tools/discover_stores.py fill in each new store's adapter settings."""
import csv, json, re, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN = ROOT / "research/handoff/data/nj_dispensary_platforms.json"
CSV = ROOT / "research/handoff/scanner/stores.csv"
OUT = ROOT / "stores.json"
SJ = {"Atlantic", "Burlington", "Camden", "Cape May", "Cumberland", "Gloucester", "Salem"}
if OUT.exists() and "--force" not in sys.argv:
    sys.exit("stores.json exists; pass --force to rebuild (this discards hand edits)")

zips = json.loads((ROOT / "data/zips.json").read_text())
scan = {r["id"]: r for r in json.loads(SCAN.read_text())}
meta = {r["id"]: r for r in csv.DictReader(open(CSV, encoding="utf-8"))}

# the eight live stores: scan id -> (our id, adapter, menu url, street address)
LIVE = {
    "daylite-cannabis-mt-laurel-township": ("daylite", {"type": "dispense", "base": "https://www.daylitecannabis.com"}, "https://www.daylitecannabis.com/menu", "1136 Route 73, Mount Laurel"),
    "nirvana-mt-laurel-township": ("nirvana", {"type": "dispense", "base": "https://explorenirvana.com"}, "https://explorenirvana.com/menu", "1134 Route 73, Mount Laurel"),
    "sage-dispensary-mt-laurel-township": ("sage", {"type": "sage"}, "https://shop.sagedispensarynj.com/rec/menu", "1170 Route 73, Mount Laurel"),
    "nar-cannabis-mt-laurel-township": ("nar", {"type": "dutchie", "id": "66edf2525a65ad64693d1605", "link": "https://shopnarcannabis.com/pages/mount-laurel-menu?dtche%5Bproduct%5D={c}"}, "https://shopnarcannabis.com/pages/mount-laurel-menu", "Mount Laurel"),
    "gynsyng-merchantville": ("gynsyng", {"type": "dutchie", "id": "65367b5ab515050009f7543a", "link": "https://www.gynsyng.com/stores/gynsyng-rec/product/{c}"}, "https://www.gynsyng.com/stores/gynsyng-rec", "Merchantville"),
    "brotherly-bud-dispensary-mt-ephraim": ("brotherlybud", {"type": "dutchie", "id": "65afc306d5271000097d57fb", "link": "https://brotherlybud.com/product/{c}/?retailer_id=14beadc1-5ad4-49df-b412-7fe5118669cc"}, "https://brotherlybud.com/shop/", "500 N Black Horse Pike, Mt Ephraim"),
    "enlighten-dispensary-marlton": ("enlighten", {"type": "dutchie", "id": "63cea036c46856007e10ab2b", "link": "https://enlightendispensary.com/?dtche%5Bproduct%5D={c}"}, "https://enlightendispensary.com/menu", "781 Route 70 W, Marlton"),
    "quality-roots-marlton": ("qualityroots", {"type": "qualityroots"}, "https://getqualityroots.com/locations/marlton/shop/", "850 Route 70 W, Marlton"),
}
SHORT = {"daylite": "Daylite", "nirvana": "Nirvana", "sage": "Sage", "nar": "NAR", "gynsyng": "Gynsyng", "brotherlybud": "Brotherly Bud",
         "enlighten": "Enlighten", "qualityroots": "Quality Roots"}
WAVE1 = {"Burlington", "Camden", "Gloucester"}


def zip_of(r, m):
    z = r.get("zip") or ""
    if not z:
        found = re.findall(r"\b(0[78]\d{3})\b", m.get("address", ""))
        z = found[-1] if found else ""
    return z


stores = {}
for sid, r in scan.items():
    m = meta.get(sid, {})
    z = zip_of(r, m)
    zc = zips.get(z)
    if not zc or zc[2] not in SJ:
        continue
    plat = r["platform"]
    live = LIVE.get(sid)
    adapter, menu, street = (live[1], live[2], live[3]) if live else ({}, r.get("menu_url") or r.get("website") or "", "")
    if not live:
        addr = re.sub(r",?\s*USA$", "", m.get("address", "")).strip()
        street = addr
        if plat == "Dutchie": adapter = {"type": "dutchie"}
        elif plat == "Dispense": adapter = {"type": "dispense"}
        elif plat == "Sweed": adapter = {"type": "sweed"}
        elif plat == "Flowhub": adapter = {"type": "flowhub"}
        else: adapter = {"type": "none"}
    typ = adapter.get("type")
    wave = 0 if live else (1 if typ in ("dutchie", "dispense") and zc[2] in WAVE1 else 2 if typ in ("dutchie", "dispense") else 3 if typ in ("sweed", "flowhub") else 9)
    stores[live[0] if live else sid] = {
        "name": SHORT.get(live[0], r["name"]) if live else r["name"], "address": street, "town": r["town"], "zip": z, "county": zc[2],
        "lat": float(m["lat"]) if m.get("lat") else zc[0], "lng": float(m["long"]) if m.get("long") else zc[1],
        "phone": m.get("phone", ""), "website": r.get("website", ""), "url": menu, "platform": plat, "scan_confidence": r["confidence"],
        "adapter": adapter, "enabled": bool(live), "medical": False, "wave": wave,
    }
names = Counter(s["name"] for s in stores.values())
for s in stores.values():  # same chain name in several towns: label by town so chips and tables stay unambiguous
    s["label"] = f'{s["name"]} ({s["town"]})' if names[s["name"]] > 1 else s["name"]
OUT.write_text(json.dumps(stores, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(len(stores), "stores written;", "waves:", sorted(Counter(s["wave"] for s in stores.values()).items()),
      "| live:", [k for k, s in stores.items() if s["wave"] == 0])
