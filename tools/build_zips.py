"""Build data/zips.json (ZIP -> [lat, lng, county]) from the Census gazetteer and ZCTA-county files.
Covers all of New Jersey (with county) plus the Philadelphia and Wilmington areas next door (county ""), because many
shoppers search from there. Used for the area picker and for assigning each store to a county.
Usage: python tools/build_zips.py <gazetteer.zip> <zcta_county_rel.txt>   (files from census.gov; see README section on stores)"""
import csv, io, json, sys, zipfile
from collections import defaultdict
from pathlib import Path

NJ = {"34001": "Atlantic", "34003": "Bergen", "34005": "Burlington", "34007": "Camden", "34009": "Cape May", "34011": "Cumberland",
      "34013": "Essex", "34015": "Gloucester", "34017": "Hudson", "34019": "Hunterdon", "34021": "Mercer", "34023": "Middlesex",
      "34025": "Monmouth", "34027": "Morris", "34029": "Ocean", "34031": "Passaic", "34033": "Salem", "34035": "Somerset",
      "34037": "Sussex", "34039": "Union", "34041": "Warren"}
gaz_zip, rel_path = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(gaz_zip) as z:
    name = [n for n in z.namelist() if n.endswith(".txt")][0]
    rows = csv.DictReader(io.TextIOWrapper(z.open(name), encoding="utf-8-sig"), delimiter="\t")
    cent = {}
    for r in rows:
        r = {k.strip(): v.strip() for k, v in r.items()}
        g = r["GEOID"]
        if (g[:2] in ("07", "08") and g >= "07001") or g[:3] in ("189", "190", "191", "197", "198", "199"):
            cent[g] = (float(r["INTPTLAT"]), float(r["INTPTLONG"]))
area = defaultdict(lambda: defaultdict(float))
with open(rel_path, encoding="utf-8-sig") as f:
    for r in csv.DictReader(f, delimiter="|"):
        z, c = r["GEOID_ZCTA5_20"], r["GEOID_COUNTY_20"]
        if z in cent and c in NJ:
            area[z][c] += float(r["AREALAND_PART"] or 0)
out = {}
for z, (la, lo) in sorted(cent.items()):
    c = max(area[z], key=area[z].get) if z in area else ""
    if c or not z.startswith(("07", "08")):
        out[z] = [round(la, 4), round(lo, 4), NJ.get(c, "")]
Path(__file__).resolve().parent.parent.joinpath("data", "zips.json").write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
print(len(out), "NJ ZIPs written")
