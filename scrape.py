"""
Pull every product from the four Mount Laurel dispensaries into products.json + index.html.

Runs a real (headless) Chromium via Playwright so each menu loads exactly as it does for
a normal visitor; we then read the same product data the page itself requests.
No keys are stored here -- anything a menu needs is taken from the live page at run time.

Usage:  python scrape.py            (writes ./out/products.json and ./out/index.html)
"""
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse, quote

from playwright.sync_api import sync_playwright

import normalize as N

OUT = Path(os.environ.get("HL_OUT") or Path(__file__).parent / "out")    # last run's data (kept private, used as fallback)
SITE = Path(os.environ.get("HL_SITE") or Path(__file__).parent / "site")  # what gets published (HL_OUT / HL_SITE redirect test runs)
PAUSE = 0.6  # seconds between paged requests -- keep it gentle
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")
BRANDS = {}  # lower-cased brand name -> {"n": name, "t": blurb, "s": store it came from}


# ----------------------------------------------------------------------------- Sage (Flowhub)
SAGE_BASE = "https://shop.sagedispensarynj.com"
SAGE_LIST = "/rec/all-products/nb/lvy"
SAGE_DATA = "?_data=%2F%3Astore%3F%2F%3Amedrec%2F%3Aname%2Fnb%2F%3Anavigation_button_slug"


def scrape_sage(ctx):
    rec = _scrape_sage_menu(ctx, "rec")
    if not N.STORES["sage"].get("medical"):
        return rec
    return N.merge_medical(rec, _scrape_sage_menu(ctx, "med"))


def _scrape_sage_menu(ctx, menu):
    listing = SAGE_LIST.replace("/rec/", f"/{menu}/")
    # Cloudflare blocks Flowhub's _data JSON route for scripts, but the normal page load is allowed and
    # embeds the same product list in window.__remixContext, so read each page from there.
    # Cloudflare also challenges headless browsers after the first page, so Sage gets a headed one
    # (needs a display); fall back to the shared headless context if none is available.
    hb = None
    try:
        hb = ctx.browser.browser_type.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        page = hb.new_context(user_agent=UA, viewport={"width": 1366, "height": 900}, locale="en-US").new_page()
    except Exception:
        page = ctx.new_page()
    try:
        items = _sage_pages(page, listing)
    finally:
        if hb:
            hb.close()
    return [sage_row(sage_compact(x), menu) for x in items]


def _sage_pages(page, listing):
    items, p, total = [], 1, 1
    while len(items) < total and p < 60:
        page.goto(f"{SAGE_BASE}{listing}?page={p}", wait_until="domcontentloaded")
        page.wait_for_function("() => window.__remixContext", timeout=30000)
        prods = page.evaluate("""() => { const ld = window.__remixContext.state.loaderData;
            const k = Object.keys(ld).find(k => ld[k] && ld[k].products && ld[k].products.products);
            return k ? ld[k].products : null; }""")
        if not prods or not prods["products"]:
            break
        total = prods["total"]
        items += prods["products"]
        p += 1
        time.sleep(PAUSE)
    return items


def sage_compact(x):
    pots = x.get("potencies") or []
    t = next((q for q in pots if q["name"] == "Total % THC"), None) or next((q for q in pots if q["name"] == "% THC"), None)
    web = (x.get("product_web_images") or [None])[0] or {}
    terps = []
    for q in x.get("terpenes") or []:
        m = re.match(r"([\d.]+)\s*(.*)", str(q.get("value") or ""))
        if m and float(m.group(1)):
            terps.append([q["name"], float(m.group(1)), m.group(2)])
    return {
        "name": x["name"], "brand": x.get("brand"), "cat": x.get("category"), "species": x.get("species"),
        "wv": x.get("weight_volume"), "uom": x.get("weight_volume_uom"), "pre": x.get("pre_tax_price"),
        "disc": x.get("pre_tax_discounted_price"), "thc": float(t["value"]) if t else None, "qty": x.get("quantity"),
        "vid": x.get("variant_id"), "desc": (x.get("description") or "").strip(),
        "cann": [[re.sub(r"^Total\s*%\s*", "Total ", re.sub(r"^%\s*", "", q["name"])), float(q["value"]), "%"]
                 for q in pots if _num(q.get("value"))],
        "terps": terps, "effects": x.get("effects") or [],
        "img": ((web.get("mobile") or {}).get("url")) or x.get("image_url"),
    }


def _num(v):
    try:
        return float(v) != 0
    except (TypeError, ValueError):
        return False


def sage_row(r, menu="rec"):
    # Flowhub names milligram doses "mg THC" (we strip the "%"), so fix their units here
    cann = [[n[3:], v, "mg"] if n.lower().startswith("mg ") else [n, v, u] for n, v, u in (r.get("cann") or [])]
    r = {**r, "cann": cann}
    thc, thc_unit = r["thc"], "%" if r["thc"] else None
    if not thc:
        mg_thc = next((v for n, v, u in cann if n == "THC" and u == "mg"), None)
        if mg_thc:
            thc, thc_unit = mg_thc, "mg"
    uom = (r["uom"] or "").lower()
    wv = r["wv"]
    grams = N.check_pack(float(wv), r["name"]) if wv and uom.startswith("gram") else N.pack_grams(r["name"])
    mg = float(wv) if wv and uom.startswith("milligram") else N.parse_mg(r["name"])
    return N.make("sage", r["name"], r["brand"], N.norm_category(r["cat"]), N.norm_strain(r["species"]), grams, mg,
                  (r["pre"] or 0) / 100, (r["disc"] or 0) / 100, thc, thc_unit,
                  N.sage_url(r["name"], r["cat"], r["vid"], menu), stock=r["qty"],
                  detail={k: r.get(k) for k in ("desc", "cann", "terps", "effects", "img")}, menu=menu)


# ----------------------------------------------------------------------------- Quality Roots (own API)
QR_API = "https://api.getqualityroots.com/products/"
QR_LOCATION = "50e8a8eb-84ff-488f-be38-672aeb398a09"  # Marlton (their site calls it Evesham)


def scrape_qualityroots(ctx):
    page = ctx.new_page()
    page.goto("https://getqualityroots.com/locations/marlton/shop/", wait_until="domcontentloaded")
    items, n, more = [], 1, True
    while more and n < 40:
        j = page.request.get(QR_API, params={"location_id": QR_LOCATION, "page": n, "page_size": 100}).json()
        items += j.get("results") or []
        more = (j.get("pagination") or {}).get("has_next")
        n += 1
        time.sleep(PAUSE)
    page.close()
    return [qr_row(qr_compact(x)) for x in items]


def qr_compact(x):
    pr, st = x.get("price") or {}, x.get("stock") or {}
    terps = []
    for t in x.get("terpenes") or []:
        for k, v in t.items():
            m = re.match(r"([\d.]+)\s*(.*)", str(v))
            if m:
                terps.append([k, float(m.group(1)), m.group(2)])
    single = pr.get("buy_quantity") in (1, None)
    return {
        "name": x.get("name"), "brand": (x.get("brand") or {}).get("name"), "cat": (x.get("category") or {}).get("name"),
        "custom": x.get("custom_category"), "ptype": x.get("product_type"), "species": x.get("species_name"),
        "grams": x.get("weight_grams"), "price": pr.get("amount"), "deal": pr.get("deal_price") if single else None,
        "qty": st.get("quantity"), "slug": x.get("slug"), "desc": x.get("description") or "",
        "cann": [[c["name"].upper(), c["upperRange"], c.get("unitOfMeasure")] for c in x.get("cannabinoid_information") or []
                 if c.get("upperRange")],
        "terps": terps, "img": x.get("image"),
    }


def qr_row(r):
    cat = N.norm_category(r.get("cat"), r.get("custom"), r.get("ptype"))
    grams = N.check_pack(r.get("grams"), r["name"]) or N.pack_grams(r["name"])
    mg = N.parse_mg(r["name"]) if not grams else None
    thc = next((v for n, v, u in r.get("cann") or [] if n == "THC"), None)
    thc_unit = next((u for n, v, u in r.get("cann") or [] if n == "THC"), None)
    return N.make("qualityroots", r["name"], r.get("brand"), cat, N.norm_strain(r.get("species")), grams, mg,
                  r.get("price"), r.get("deal"), thc, "mg" if (thc_unit or "").lower() == "mg" else ("%" if thc else None),
                  f"https://getqualityroots.com/product/{r['slug']}/", stock=r.get("qty"),
                  detail={k: r.get(k) for k in ("desc", "cann", "terps", "img")})


# ----------------------------------------------------------------------------- Dutchie stores
# Every store here runs on Dutchie. We open one Dutchie menu, copy its list + detail query URLs,
# and replay them with each store's dispensary id. To add a Dutchie store, add a line here.
def _link_fn(template):
    """Deep link to one product: the registry's template with {c} (the product's cName) filled in. No {c}: just the menu page."""
    return lambda c: template.replace("{c}", quote(c))


DUTCHIE = {k: {"id": v["adapter"]["id"], "link": _link_fn(v["adapter"].get("link") or v["url"])}
           for k, v in N.STORES.items() if v["adapter"].get("type") == "dutchie" and v["adapter"].get("id")}
DUTCHIE_SEED_MENU = "https://dutchie.com/embedded-menu/nar-cannabis-mt-laurel/products/flower"


def _gql(page, url):
    return page.evaluate("async (u) => (await fetch(u, {headers: {'content-type': 'application/json'}})).json()", url)


def _with_vars(u, qs, variables):
    q = dict(qs)
    q["variables"] = json.dumps(variables, separators=(",", ":"))
    return urlunparse(u._replace(query=urlencode(q)))


_DUTCHIE_Q = {}


def _dutchie_queries(ctx):
    """Load one Dutchie menu + product page and copy the two query URLs it uses (cached per run)."""
    if _DUTCHIE_Q:
        return _DUTCHIE_Q
    page = ctx.new_page()
    with page.expect_request(lambda r: "operationName=FilteredProducts" in r.url, timeout=45000) as req:
        page.goto(DUTCHIE_SEED_MENU, wait_until="domcontentloaded")
    lu = urlparse(req.value.url)
    lqs = {k: v[0] for k, v in parse_qs(lu.query).items()}
    lvars = json.loads(lqs["variables"])
    lvars["productsFilter"]["types"] = []
    lvars["perPage"] = 100
    _DUTCHIE_Q["list"] = (lu, lqs, lvars)
    first = ((_gql(page, _with_vars(lu, lqs, {**lvars, "page": 0})).get("data") or {})
             .get("filteredProducts") or {}).get("products") or []
    if first:
        try:
            with page.expect_request(lambda r: "operationName=IndividualFilteredProduct" in r.url, timeout=30000) as dreq:
                page.goto(DUTCHIE_SEED_MENU.replace("/products/flower", "/product/" + first[0]["cName"]),
                          wait_until="domcontentloaded")
            du = urlparse(dreq.value.url)
            dqs = {k: v[0] for k, v in parse_qs(du.query).items()}
            dvars = json.loads(dqs["variables"])
            dvars["productsFilter"].pop("cName", None)
            _DUTCHIE_Q["detail"] = (du, dqs, dvars)
        except Exception as e:
            print("dutchie: detail query not found:", e, file=sys.stderr)
    _DUTCHIE_Q["page"] = page  # reuse this dutchie.com page for all stores' requests
    return _DUTCHIE_Q


def scrape_dutchie(ctx, store):
    rec = _scrape_dutchie_menu(ctx, store, "rec")
    if not N.STORES[store].get("medical"):
        return rec
    return N.merge_medical(rec, _scrape_dutchie_menu(ctx, store, "med"))


def _scrape_dutchie_menu(ctx, store, menu):
    """1) list query -> every product id; 2) detail query in batches of 100 ids
    (adds description, terpenes, effects, brand blurb)."""
    cfg = DUTCHIE[store]
    Q = _dutchie_queries(ctx)
    page = Q["page"]
    lu, lqs, lvars = Q["list"]
    lvars = json.loads(json.dumps(lvars))
    lvars["productsFilter"]["dispensaryId"] = cfg["id"]
    lvars["productsFilter"]["pricingType"] = menu

    # Dutchie pages hold 93-100 products, not always 100, so "short page = last page" drops most of a menu.
    # Trust the page count Dutchie reports (queryInfo.totalPages); fall back to "empty page" if it is missing.
    listed, pg, total_pages = [], 0, None
    while pg < 80:
        lvars["page"] = pg
        fp = (_gql(page, _with_vars(lu, lqs, lvars)).get("data") or {}).get("filteredProducts") or {}
        batch = fp.get("products") or []
        listed += batch
        if total_pages is None:
            total_pages = (fp.get("queryInfo") or {}).get("totalPages")
        pg += 1
        if not batch or (total_pages is not None and pg >= total_pages):
            break
        time.sleep(PAUSE)
    listed = list({p["id"]: p for p in listed}.values())  # a product can show up on two pages

    detailed = {}
    if listed and "detail" in Q:
        du, dqs, dvars = Q["detail"]
        dvars = json.loads(json.dumps(dvars))
        dvars["productsFilter"]["dispensaryId"] = cfg["id"]
        ids = [p["id"] for p in listed]
        for i in range(0, len(ids), 100):
            dvars["productsFilter"]["productIds"] = ids[i:i + 100]
            for p in (_gql(page, _with_vars(du, dqs, dvars)).get("data") or {}).get("filteredProducts", {}).get("products") or []:
                detailed[p["id"]] = p
            time.sleep(PAUSE)
    for p in detailed.values():
        b = p.get("brand") or {}
        if b.get("name") and b.get("description"):
            k = b["name"].strip().lower()
            if k not in BRANDS or len(b["description"]) > len(BRANDS[k]["t"]):
                BRANDS[k] = {"n": b["name"], "t": b["description"].strip(), "s": store}
    out = []
    for p in listed:
        out += dutchie_rows(store, nar_compact(detailed.get(p["id"], p)), menu)
    return out


def nar_compact(p):
    U = {"PERCENTAGE": "%", "MILLIGRAMS": "mg"}
    t = p.get("THCContent") or {}
    thc, unit = (t.get("range") or [None])[0], t.get("unit")
    cann = [[(c.get("cannabinoid") or {}).get("name"), c["value"], U.get(c.get("unit"), c.get("unit"))]
            for c in p.get("cannabinoidsV2") or [] if c.get("value")]
    if not thc:
        for n, v, u in cann:
            if n and "THC" in n:
                thc, unit = v, "PERCENTAGE" if u == "%" else "MILLIGRAMS"
                break
    return {
        "name": p.get("Name"), "brand": p.get("brandName"), "type": p.get("type"), "sub": p.get("subcategory"),
        "strain": p.get("strainType"), "opts": p.get("Options") or [], "prices": p.get("recPrices") or p.get("Prices") or [],
        "special": p.get("recSpecialPrices") or [], "medPrices": p.get("medicalPrices") or [],
        "medSpecial": p.get("medicalSpecialPrices") or [], "thc": thc, "thcUnit": unit, "cname": p.get("cName"),
        "desc": (p.get("description") or "").strip(), "cann": cann,
        "terps": [[(x.get("libraryTerpene") or {}).get("name"), x["value"], x.get("unitSymbol") or x.get("unit")]
                  for x in p.get("terpenes") or [] if x.get("value")],
        "effects": [k for k, v in sorted((p.get("effects") or {}).items(), key=lambda kv: -(kv[1] or 0)) if v],
        "img": p.get("Image"),
        "stock": [c.get("quantity") for c in ((p.get("POSMetaData") or {}).get("children") or [])],
    }


def dutchie_rows(store, r, menu="rec"):
    out = []
    cat = N.norm_category(r["type"], r["sub"])
    detail = {k: r.get(k) for k in ("desc", "cann", "terps", "effects", "img")}
    link = DUTCHIE[store]["link"](r["cname"]) if r.get("cname") else None
    prices, specials = (r["prices"], r["special"]) if menu == "rec" else \
        (r.get("medPrices") or r["prices"], r.get("medSpecial") or [])
    # With several size options (say a 2-pack and a 5-pack) the name can't overrule an option's own weight.
    single = (lambda g: N.check_pack(g, r["name"])) if len(r["opts"] or []) <= 1 else (lambda g: g)
    for i, opt in enumerate(r["opts"] or [None]):
        price = prices[i] if i < len(prices) else None
        if price is None:
            continue
        sale = specials[i] if i < len(specials) else None
        stock = r["stock"][i] if i < len(r.get("stock") or []) else None
        out.append(N.make(
            store, r["name"], r["brand"], cat, N.norm_strain(r["strain"]),
            single(N.parse_grams(opt)) or N.pack_grams(r["name"]), N.parse_mg(r["name"], opt), price, sale,
            r["thc"] or None, {"PERCENTAGE": "%", "MILLIGRAMS": "mg"}.get(r["thcUnit"]),
            link, size=opt, stock=stock, detail=detail, menu=menu))
    return out


# ----------------------------------------------------------------------------- Daylite + Nirvana (Dispense)
DISPENSE = {k: v["adapter"]["base"] for k, v in N.STORES.items() if v["adapter"].get("type") == "dispense" and v["adapter"].get("base")}
DISPENSE_PATH = {k: v["adapter"]["menu_path"] for k, v in N.STORES.items() if v["adapter"].get("menu_path")}  # sites that serve the menu under /shop instead of /menu
# Dispense runs medical as a separate menu ("venue"). If a store turns one on, put its menu site here.
DISPENSE_MED = {}


def _pass_age_gate(page):
    for label in ("I am 21 or older", "Yes", "I'm 21", "Enter"):
        btn = page.get_by_role("button", name=label)
        try:
            if btn.count():
                btn.first.click(timeout=2000)
                return
        except Exception:
            pass


def scrape_dispense(ctx, store):
    # Own browser context per store: reusing one after Daylite left Nirvana's menu without a products request.
    own = ctx.browser.new_context(user_agent=UA, viewport={"width": 1366, "height": 900})
    try:
        rec = _scrape_dispense_menu(own, store, DISPENSE[store], "rec")
        if not (N.STORES[store].get("medical") and DISPENSE_MED.get(store)):
            return rec
        return N.merge_medical(rec, _scrape_dispense_menu(own, store, DISPENSE_MED[store], "med"))
    finally:
        own.close()


def _scrape_dispense_menu(ctx, store, base, menu):
    """Load a menu page, make it ask the Dispense API for products (by typing in its search box,
    falling back to scrolling), copy that request's headers, then page through the whole menu."""
    page = ctx.new_page()
    captured = {}

    def on_request(r):
        if "api.dispenseapp.com" in r.url and "/products" in r.url and not captured:
            captured["url"] = r.url
            captured["headers"] = {k: v for k, v in r.headers.items()
                                   if k.lower() in ("api-key", "x-prospect-token", "x-pathname", "x-url")}

    page.on("request", on_request)
    page.goto(base + DISPENSE_PATH.get(store, "/menu/categories/flower"), wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    _pass_age_gate(page)
    try:
        box = page.get_by_placeholder("Search products").first
        box.click(timeout=5000)
        box.type("blue", delay=80)
        page.wait_for_timeout(3000)
    except Exception:
        pass
    for _ in range(15):
        if captured:
            break
        page.mouse.wheel(0, 4000)
        page.wait_for_timeout(1200)
    if not captured:
        page.close()
        raise RuntimeError(f"{store}: menu never requested products from Dispense")

    u = urlparse(captured["url"])
    venue = u.path.split("/venues/")[1].split("/")[0]
    api = f"{u.scheme}://{u.netloc}/v1/venues/{venue}"
    hdr = captured["headers"]

    # one venue-wide endpoint returns the whole menu (100 per page, with a total `count`)
    items, skip, count = [], 0, 1
    while skip < count and skip < 5000:
        j = page.request.get(
            f"{api}/products",
            params={"limit": 100, "skip": skip, "quantityMin": 1, "orderPickUpType": "IN_STORE"},
            headers=hdr,
        ).json()
        count = j.get("count", 0)
        items += j.get("data") or []
        skip += 100
        time.sleep(PAUSE)
    page.close()
    for x in items:
        b = x.get("brand") or {}
        if b.get("name") and b.get("description"):
            k = b["name"].strip().lower()
            if k not in BRANDS or len(b["description"]) > len(BRANDS[k]["t"]):
                BRANDS[k] = {"n": b["name"], "t": b["description"].strip(), "s": store}
    return [dispense_row(store, base, dispense_compact(x), menu) for x in items]



DISPENSE_CANN = {"thc": "THC", "thcA": "THC-A", "cbd": "CBD", "cbdA": "CBD-A", "cbn": "CBN", "cbg": "CBG",
                 "thcv": "THCV", "cbc": "CBC"}


def dispense_compact(x):
    labs = x.get("labs") or {}
    cann, terps = [], []
    for k, unit in labs.items():
        if not k.endswith("ContentUnit"):
            continue
        base_key = k[:-len("ContentUnit")]
        v = labs.get(base_key)
        if not isinstance(v, (int, float)) or not v:
            continue
        if base_key in DISPENSE_CANN:
            cann.append([DISPENSE_CANN[base_key], v, unit or ""])
        else:
            terps.append([re.sub(r"([A-Z])", r" \1", base_key).strip().title(), v, unit or ""])
    img = x.get("image")
    return [
        x.get("name"), (x.get("brand") or {}).get("name"), x.get("productCategoryName"),
        x.get("cannabisComplianceType"), x.get("subType"), x.get("cannabisType"), x.get("weightInGrams"),
        x.get("weightFormatted"), x.get("weightUnit"), x.get("price"), x.get("priceWithDiscounts"),
        labs.get("thc"), labs.get("thcContentUnit"), x.get("quantity"), x.get("productUrl"),
        {"desc": x.get("description") or "", "cann": cann, "terps": terps,
         "effects": [str(e).replace("-", " ") for e in x.get("effects") or []],
         "img": f"{img}?w=320&auto=format" if img else None},
    ]


def dispense_row(store, base, r, menu="rec"):
    (name, brand, catname, ctype, subtype, strain, wg, wf, wunit, price, price_disc, thc, thc_unit,
     qty, url) = r[:15]
    detail = r[15] if len(r) > 15 else None
    cat = N.norm_category(catname, ctype, subtype)
    grams = N.check_pack(wg, name) if wunit in ("GRAMS", "OUNCES") and wg else (N.check_pack(N.parse_grams(wf), name) or N.pack_grams(name))
    mg = N.parse_mg(wf, name) if not grams else None
    return N.make(store, name, brand, cat, N.norm_strain(strain), grams, mg, price, price_disc,
                  thc, "%" if thc_unit in (None, "%") else thc_unit, url or f"{base}/menu",
                  size=wf, stock=qty, detail=detail, menu=menu)


# ----------------------------------------------------------------------------- main
def main():
    """python scrape.py [--only id1,id2]: --only scrapes just those stores; every other store keeps its last data."""
    only = set(sys.argv[sys.argv.index("--only") + 1].split(",")) if "--only" in sys.argv else None
    OUT.mkdir(exist_ok=True)
    results, status = [], {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(
            user_agent=UA,
            viewport={"width": 1366, "height": 900},
        )
        active = N.active_stores()
        jobs = []
        for typ in ("sage", "qualityroots", "dutchie", "dispense"):  # Sage first: it opens a visible browser
            for name, st in active.items():
                if st["adapter"]["type"] != typ:
                    continue
                fn = {"sage": scrape_sage, "qualityroots": scrape_qualityroots,
                      "dutchie": lambda c, k=name: scrape_dutchie(c, k),
                      "dispense": lambda c, k=name: scrape_dispense(c, k)}[typ]
                jobs.append((name, fn))
        jobs = [(name, fn) for name, fn in jobs if name in active and (only is None or name in only)]
        for name, fn in jobs:
            t0 = time.time()
            try:
                for attempt in (1, 2, 3):  # menus occasionally fail to fire their product request
                    try:
                        rows = [r for r in fn(ctx) if N.keep(r)]
                        break
                    except Exception:
                        if attempt == 3:
                            raise
                        time.sleep(5)
                results += rows
                status[name] = {"ok": True, "count": len(rows), "seconds": round(time.time() - t0)}
            except Exception as e:  # one broken store shouldn't sink the rest
                status[name] = {"ok": False, "error": str(e)[:300], "seconds": round(time.time() - t0)}
            print(name, status[name], file=sys.stderr)
        browser.close()

    # keep last good data for any store that failed this run (and, with --only, for every store not scraped)
    prev_path = OUT / "products.json"
    if prev_path.exists():
        prev = json.loads(prev_path.read_text(encoding="utf-8"))
        for name in active:
            if only is not None and name not in only and name not in status:
                results += [r for r in prev.get("products", []) if r["store"] == name]
                status[name] = {**prev.get("status", {}).get(name, {"ok": True}), "carried": True}
        for name, st in status.items():
            if not st["ok"] and not st.get("carried"):
                kept = [r for r in prev.get("products", []) if r["store"] == name]
                results += kept
                st["stale_rows_kept"] = len(kept)
                st["last_ok"] = prev.get("status", {}).get(name, {}).get("last_ok")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for name, st in status.items():
        if st["ok"] and not st.get("carried"):
            st["last_ok"] = now

    brands = dict(json.loads(prev_path.read_text(encoding="utf-8")).get("brands", {})) if prev_path.exists() else {}
    brands.update(BRANDS)
    results = [r for r in results if r["store"] in active]
    payload = {"updated": now, "stores": active, "status": status, "brands": brands, "products": results}
    prev_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    build_html(payload)
    print(f"wrote {len(results)} products -> {SITE / 'index.html'}", file=sys.stderr)
    if not any(st["ok"] for st in status.values()):
        print("Every store failed this run; not safe to deploy.", file=sys.stderr)
        sys.exit(1)


def load_affiliates():
    """Affiliate tiles + sponsored slot for the page. HL_AFFILIATES=<file> overrides affiliates.json (for previews).
    With go_base set, tiles link to go_base + id and the redirect service holds the real URLs (they stay out of the page).
    With go_base blank, tiles link straight to each item's https url."""
    path = Path(os.environ.get("HL_AFFILIATES") or Path(__file__).parent / "affiliates.json")
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    go = (cfg.get("go_base") or "").strip()
    cats = {}
    for cat, c in (cfg.get("categories") or {}).items():
        items = []
        for i in c.get("items", []):
            if not (i.get("id") and i.get("title") and i.get("enabled", True)):
                continue
            if not go and not str(i.get("url", "")).startswith("https://"):
                continue  # direct mode needs a usable https link
            t = {k: i.get(k, "") for k in ("id", "title", "merchant", "price", "img")}
            if not go:
                t["url"] = i["url"]  # no redirect service: tile links straight to the merchant
            items.append(t)
        if items:
            cats[cat] = {"heading": c.get("heading", ""), "items": items}
    sp = cfg.get("sponsored") or {}
    spon = {k: sp.get(k, "") for k in ("label", "text", "cta", "url")} if sp.get("enabled") and sp.get("url") and sp.get("text") else None
    if spon and go:
        spon["url"] = ""  # clicks go through go_base + "sponsor"
    if not cats and not spon:
        return None
    return {"go": go, "disclosure": cfg.get("disclosure", ""), "categories": cats, "sponsored": spon}


DEFAULT_ZIP = "08054"  # Mount Laurel: the area first-time visitors see


def _hue(store_id):
    return int(hashlib.md5(store_id.encode()).hexdigest()[:4], 16) % 360


def public_stores():
    """What the page needs to know about each live store (no scraper settings)."""
    keys = ("name", "label", "address", "town", "zip", "county", "lat", "lng", "url", "medical")
    return {k: {**{x: v.get(x) for x in keys}, "hue": _hue(k)} for k, v in N.active_stores().items()}


def _dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def write_shards(payload, store_ids):
    """One small file per store (the prices) plus one for its details (descriptions, terpenes, ...) that the page
    only fetches when someone opens a product. Row i of <id>.json has its detail under key "i" in <id>.d.json."""
    out = SITE / "data"
    out.mkdir(parents=True, exist_ok=True)
    by = {}
    for r in payload["products"]:
        by.setdefault(r["store"], []).append(r)
    keep = {"brands.json", "zips.json"}
    for sid in store_ids:
        core, det = [], {}
        for i, r in enumerate(by.get(sid, [])):
            r = dict(r)
            d = r.pop("d", None)
            r.pop("store", None)  # same for every row in the file; the page adds it back
            core.append(r)
            if d:
                det[str(i)] = d
        _dump(out / f"{sid}.json", {"rows": core})
        _dump(out / f"{sid}.d.json", det)
        keep |= {f"{sid}.json", f"{sid}.d.json"}
    _dump(out / "brands.json", payload.get("brands", {}))
    zips = Path(__file__).parent / "data" / "zips.json"
    if zips.exists():
        (out / "zips.json").write_bytes(zips.read_bytes())
    for f in out.glob("*.json"):  # drop files for stores that are no longer live
        if f.name not in keep:
            f.unlink()
    return {sid: len(by.get(sid, [])) for sid in store_ids}


def build_html(payload):
    """Write site/data/*.json (per-store prices) and site/index.html (the page plus the small store list)."""
    tpl = (Path(__file__).parent / "template.html").read_text(encoding="utf-8")
    stores = public_stores()
    counts = write_shards(payload, list(stores))
    status = {k: {"ok": st.get("ok", True), "count": counts.get(k, 0), "last_ok": st.get("last_ok")}
              for k, st in payload["status"].items() if k in stores}
    zc = json.loads((Path(__file__).parent / "data" / "zips.json").read_text(encoding="utf-8"))[DEFAULT_ZIP]
    page = {"default_area": {"zip": DEFAULT_ZIP, "radius": 15, "lat": zc[0], "lng": zc[1]},
            "updated": payload["updated"], "v": re.sub(r"\D", "", payload["updated"])[:14], "stores": stores, "status": status,
            "affiliates": load_affiliates()}
    data = json.dumps(page, ensure_ascii=False).replace("</", "<\\/").replace("\ufffd", "")
    SITE.mkdir(exist_ok=True)
    (SITE / "index.html").write_text(tpl.replace("/*__DATA__*/null", data), encoding="utf-8")
    logo = Path(__file__).parent / "logo.png"
    if logo.exists():
        (SITE / "favicon.png").write_bytes(logo.read_bytes())


if __name__ == "__main__":
    main()
