"""Shared normalization: turn each store's raw rows into one product schema."""
import json
import os
import re
from pathlib import Path
from urllib.parse import quote

# Stores live in stores.json (the registry): name, address, coordinates, platform, scraper settings, and
# "enabled": true/false, which switches a store on or off without deleting its settings.
# "medical": true means the store sells to medical patients online; the scraper then also pulls its medical menu
# and the page shows a Rec / Med / Both switch. HL_STORES=<file> points at a different registry (for tests).
REGISTRY_PATH = Path(os.environ.get("HL_STORES") or Path(__file__).parent / "stores.json")
STORES = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def adapter_ready(store):
    """A store can be scraped only when its adapter has everything it needs."""
    a = store.get("adapter") or {}
    t = a.get("type")
    return t in ("sage", "qualityroots") or (t == "dutchie" and bool(a.get("id"))) or (t == "dispense" and bool(a.get("base")))


CATEGORY_MAP = [
    (r"pre[\s-]?rolls?|joint|blunt|infused cone", "Pre-Rolls"),
    (r"vape|vapori|cart|pod|aio|disposable", "Vapes"),
    (r"concentrate|extract|wax|rosin|resin|shatter|badder|budder|diamond|sauce|hash|kief", "Concentrates"),
    (r"beverage|drink|liquid", "Beverages"),
    (r"edible|gumm|chocolate|chew|mint|tablet|capsule|lozenge", "Edibles"),
    (r"tincture|oral", "Tinctures"),
    (r"topical|lotion|balm|salve", "Topicals"),
    (r"flower|shake|smalls|bud", "Flower"),
    (r"accessor|merch|gear|battery|paraphernalia|apparel", "Accessories"),
    (r"cbd", "CBD"),
]


def norm_category(*hints):
    """Hints in priority order (store's own category first); first hint that maps wins."""
    for h in hints:
        if not h:
            continue
        text = str(h).lower()
        for pat, cat in CATEGORY_MAP:
            if re.search(pat, text):
                return cat
    return "Other"


def norm_strain(s):
    s = (s or "").lower()
    if not s:
        return None
    if "indica" in s:
        return "Indica" if "hybrid" not in s and "dom" not in s else "Indica-Hybrid"
    if "sativa" in s:
        return "Sativa" if "hybrid" not in s and "dom" not in s else "Sativa-Hybrid"
    if "hybrid" in s or "50/50" in s or "balanced" in s:
        return "Hybrid"
    if "cbd" in s or "high" in s:
        return "CBD"
    return None


OZ_FRACTIONS = {"1/8": 3.5, "1/4": 7.0, "1/2": 14.0}
# A whole number: "0.5", "0,5" and ".5" (menus write all three), never just the "5" inside them.
# A comma right after a word is a separator ("Rainbow,3.5g"), so a decimal comma needs a digit before it.
NUM = r"(?<!\d)(?<!\d[.,])(\d+(?:[.,]\d+)?|\.\d+)"


def _num(s):
    """'0,5' and '.5' are decimals; '1,000' is a thousands separator."""
    if re.fullmatch(r"\d{1,3},\d{3}", s):
        return float(s.replace(",", ""))
    return float(s.replace(",", "."))


def parse_grams(*texts):
    """Find a flower/concentrate weight in grams from sizes or names. Returns None for mg-only items."""
    for t in texts:
        if not t:
            continue
        t = str(t).lower()
        m = re.search(r"(1/8|1/4|1/2)\s*(oz|ounce)", t)
        if m:
            return OZ_FRACTIONS[m.group(1)]
        m = re.search(NUM + r"\s*oz\b", t)
        if m:
            return round(_num(m.group(1)) * 28, 2)
        m = re.search(NUM + r"\s*(g|gr|gram|grams)\b", t)
        if m:
            return _num(m.group(1))
    return None


# "5pk", "5 pk", "5-Pack", "10 ct", "10 x .3g", "2pk x 0.75g"
PACK = re.compile(r"(?<![\d.])(\d{1,2})\s*-?\s*(?:pk|pack|ct|count|pcs?)\b|(?<![\d.])(\d{1,2})\s*x\s*(?=[.\d])", re.I)


def pack_grams(name):
    """Weight of the whole pack, from a product name. Names give either the pack total ("5pk 2.5g", "3.5g/6pk") or
    one unit ("5pk .5g", "0.58G | 6PK", "10 x .3g", "2pk x 0.75g each"). A weight under 1g, or one marked "each"
    or written "N x weight", is one unit; anything else is taken as the total. Only for weights read from a name:
    stores' own weight fields and size options already give the total."""
    g = parse_grams(name)
    m = PACK.search(name or "")
    n = int(m.group(1) or m.group(2)) if m else 1
    if not g or n < 2:
        return g
    per_unit = g < 1 or re.search(r"(?i)\beach\b", name) or m.group(2)
    return round(g * n, 2) if per_unit else g


def parse_mg(*texts):
    for t in texts:
        if not t:
            continue
        m = re.search(NUM + r"\s*mg\b", str(t).lower())
        if m:
            return _num(m.group(1))
    return None


def size_label(grams, mg, fallback=None):
    if grams:
        return f"{grams:g}g"
    if mg:
        return f"{mg:g}mg"
    return fallback or ""


STOP = {"flower", "pre", "roll", "preroll", "prerolls", "pre-roll", "vape", "cart", "cartridge", "aio", "the", "and",
        "g", "mg", "oz", "ct", "pack", "pk", "indica", "sativa", "hybrid", "whole", "smalls", "popcorn", "buds",
        "mixed", "prepack", "live", "resin", "rosin", "gummies", "gummy", "reserve", "cannabis"}


def match_key(brand, name, category, grams, mg):
    """Loose key so the same product at different stores groups together."""
    b = re.sub(r"[^a-z0-9]", "", (brand or "").lower())
    n = (name or "").lower()
    if brand:
        n = n.replace(brand.lower(), " ")
    n = re.sub(r"\d+(\.\d+)?\s*(mg|g|oz|ct|pk)\b|1/8|1/4|1/2", " ", n)
    toks = sorted(set(t for t in re.findall(r"[a-z0-9]+", n) if t not in STOP and len(t) > 1))
    return f"{b}|{category}|{' '.join(toks)}|{grams or mg or ''}"


def make(store, name, brand, category, strain, grams, mg, price, sale_price, thc, thc_unit, url, size=None, stock=None,
         detail=None, menu="rec"):
    if re.search(r"(?i)\bboveda\b|humidity (control|pack)|\bgrinder\b|\blighter\b|rolling papers?|pre-rolled tips|\btips\b|king palm|\bwraps?\b|\bbattery\b|\bhoodie\b|t-shirt", name or ""):
        category = "Accessories"
    if category in ("Edibles", "Beverages", "Tinctures", "Topicals", "CBD"):
        # package weights (a "1g" gummy option, a 40g bag) mislead here; dose in mg is what matters
        grams = None
        mg = parse_mg(name) or mg
        size = size if size and re.search(r"(?i)mg|ml|\bct\b|pk|pack|oz", str(size)) else None
    price = round(float(price), 2) if price is not None else None
    sale = round(float(sale_price), 2) if sale_price not in (None, 0) and price and sale_price < price else None
    eff = sale if sale is not None else price
    ppg = round(eff / grams, 2) if eff and grams and category in ("Flower", "Pre-Rolls", "Concentrates", "Vapes") else None
    return {
        "store": store,
        "name": (name or "").strip(),
        "brand": (brand or "").strip() or None,
        "category": category,
        "strain": strain,
        "size": size_label(grams, mg, size),
        "grams": grams,
        "mg": mg,
        "price": price,
        "sale_price": sale,
        "price_now": eff,
        "per_gram": ppg,
        "thc": thc,
        "thc_unit": thc_unit,
        "stock": stock,
        "url": url,
        "key": match_key(brand, name, category, grams, mg),
        "d": clean_detail(detail),
        **({"menu": "med"} if menu == "med" else {}),
    }


def clean_html(t):
    """Store descriptions sometimes arrive as HTML; keep plain paragraphs."""
    if not t:
        return ""
    t = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</div>", "\n", str(t))
    t = re.sub(r"<[^>]+>", "", t)
    t = (t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#39;", "'").replace("&quot;", '"')
          .replace("&lt;", "<").replace("&gt;", ">"))
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n\n", t).strip()


def clean_detail(d):
    """detail = {desc, cann:[[name,value,unit]], terps:[[name,value,unit]], effects:[str], img}; drop empties."""
    if not d:
        return None
    out = {}
    desc = clean_html(d.get("desc"))
    if desc and len(desc) > 2:
        out["desc"] = desc[:2500]
    for k in ("cann", "terps"):
        rows = [[n, round(float(v), 3), u or ""] for n, v, u in (d.get(k) or []) if n and v not in (None, "", 0)]
        if rows:
            out[k] = sorted(rows, key=lambda r: -r[1])[:14]
    eff = [e.strip().title() for e in (d.get("effects") or []) if e and e.strip()]
    if eff:
        out["effects"] = list(dict.fromkeys(eff))[:8]
    if d.get("img"):
        out["img"] = d["img"]
    return out or None


def keep(row):
    """Drop sample/display items and zero-dollar placeholders."""
    n = row["name"].lower()
    if re.search(r"\bsample\b|\bdisplay\b|\btester\b", n):
        return False
    return bool(row["price_now"]) and row["price_now"] >= 1


def sage_url(name, category, variant_id, menu="rec"):
    """Sage (Flowhub) product page; the variant id is what actually selects the product."""
    if not variant_id:
        return "https://shop.sagedispensarynj.com/rec/menu"
    slug = quote(re.sub(r"\s+", "-", (name or "").lower()), safe="()!*'.-_~")
    return f"https://shop.sagedispensarynj.com/{menu}/{(category or 'products').lower()}/pdp/{slug}/v/{variant_id}"


def nar_url(cname):
    """Opens NAR's own menu page with the Dutchie embed jumped to this product."""
    base = "https://shopnarcannabis.com/pages/mount-laurel-menu"
    return f"{base}?dtche%5Bproduct%5D={quote(cname)}" if cname else base


def merge_medical(rec_rows, med_rows):
    """Medical listings are kept only when they add something: a different price, or a product
    rec customers can't buy. When the medical price matches, the rec listing is marked med_same."""
    by_key = {(r["store"], r["name"].strip().lower(), r["size"]): r for r in rec_rows}
    extra = []
    for m in med_rows:
        r = by_key.get((m["store"], m["name"].strip().lower(), m["size"]))
        if r is None:
            m["med_only"] = True
            extra.append(m)
        elif r["price_now"] == m["price_now"]:
            r["med_same"] = True
        else:
            extra.append(m)
    return rec_rows + extra


def active_stores():
    """Stores that are switched on and ready to scrape."""
    return {k: v for k, v in STORES.items() if v.get("enabled", False) and adapter_ready(v)}
