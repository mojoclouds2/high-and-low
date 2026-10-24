"""
NJ dispensary menu-platform scanner.

Commands
  python crawl.py discover            Load the state's dispensary map, save raw captures + a candidate store list
  python crawl.py detect [options]    Visit each store in stores.csv and work out which menu platform it uses
  python crawl.py summary             Count stores per platform and write results.csv

Everything is written next to this file. detect is resumable: stop with Ctrl+C, run it again, it skips finished stores.
"""
import argparse, csv, json, random, re, sys, time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urljoin

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
STORES = HERE / "stores.csv"
CANDIDATES = HERE / "stores_candidates.csv"
RESULTS = HERE / "results.jsonl"
MAP_URL = "https://my.atlist.com/map/8bed33fa-9b8c-4c51-bb33-74cd0d98628a?share=true"
FIND_URL = "https://www.nj.gov/cannabis/dispensaries/find/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36")

STRONG, MED, WEAK = 3, 2, 1

# hosts: matched against hostnames the page requests (strong) and iframe sources (strong)
# html:  regexes matched against page HTML (medium: footer credits, links, URL patterns)
# frame_only: marketplaces that only count when the menu is actually embedded
SIGS = {
    "Dutchie":   {"hosts": ["dutchie.com"], "html": [r"dutchie\.com", r"dtche[=_]", r"embedded-menu"]},
    "Jane":      {"hosts": ["iheartjane.com"], "html": [r"iheartjane\.com", r"jane[-_ ]?roots", r"jane-frame"]},
    "Dispense":  {"hosts": ["dispenseapp.com", "dispense-images.imgix.net"], "html": [r"dispenseapp\.com", r"dispense-images\.imgix"]},
    "Flowhub":   {"hosts": ["flowhub.com", "dispensary.shop"], "html": [r"by\s+Flowhub", r"flowhub\.com", r"dispensary\.shop"]},
    "LeafBridge": {"hosts": ["leafbridge.io"], "html": [r"leafbridge\.io", r"Menu by LeafBridge"]},
    "Sweed":     {"hosts": ["sweedpos.com"], "html": [r"sweedpos", r"sweed\.io"]},
    "Treez":     {"hosts": ["treez.io", "treezpay.com"], "html": [r"treez\.io"]},
    "Blaze":     {"hosts": ["blaze.me", "blazepos.com"], "html": [r"blaze\.me", r"blazepos"]},
    "Meadow":    {"hosts": ["getmeadow.com"], "html": [r"getmeadow\.com"]},
    "Tymber":    {"hosts": ["tymber.io"], "html": [r"tymber\.io"]},
    "Olla":      {"hosts": ["getolla.com", "olla.com"], "html": [r"getolla\.com"]},
    "Cova":      {"hosts": ["covasoft.net", "cova.software"], "html": [r"covasoft", r"cova\.software"]},
    "POSaBIT":   {"hosts": ["posabit.com"], "html": [r"posabit"]},
    "Herb.co (Aggle)": {"hosts": ["herb.co", "aggle.net"], "html": []},
    "Hytiva":    {"hosts": ["hytiva.com"], "html": []},
    "Proteus420": {"hosts": ["proteuserp.com", "proteus420.com"], "html": []},
    "Carrot":    {"hosts": ["getcarrot.io"], "html": []},
    "Joint Commerce": {"hosts": ["jointcommerce.com"], "html": []},
    "Hashly":    {"hosts": ["wearehashly.co", "hashly.co"], "html": []},
    "Shopify (custom storefront)": {"hosts": ["cdn.shopify.com", "myshopify.com"], "html": [r"/collections/", r"Shopify\.theme"]},
    "Weedmaps embed": {"hosts": ["weedmaps.com"], "html": [], "frame_only": True},
    "Leafly embed":   {"hosts": ["leafly.com"], "html": [], "frame_only": True},
}

NOISE = ("google", "gstatic", "googletagmanager", "doubleclick", "facebook", "fbcdn", "instagram", "twitter",
         "tiktok", "linkedin", "youtube", "ytimg", "cloudflare", "cdn-cgi", "gravatar", "wp.com",
         "jquery", "bootstrapcdn", "fontawesome", "typekit", "hotjar", "clarity.ms", "segment", "sentry",
         "recaptcha", "hcaptcha", "newrelic", "onetrust", "cookiebot", "klaviyo", "alpineiq", "twimg",
         "launchdarkly", "userway", "ethyca", "doubleclick", "analytics", "posthog", "mixpanel", "amplitude",
         "intercom", "zendesk", "stripe", "paypal", "tiktok", "pinterest", "snapchat", "bing.com", "clarity")
SOCIAL = ("facebook.com", "instagram.com", "twitter.com", "x.com", "linkedin.com", "tiktok.com",
          "youtube.com", "google.com", "goo.gl", "atlist.com", "yelp.com", "nj.gov")


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def first(d, names):
    low = {k.lower(): v for k, v in d.items()}
    for n in names:
        v = low.get(n)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def norm_url(u):
    u = (u or "").strip()
    if not u:
        return ""
    if not re.match(r"^https?://", u, re.I):
        if "." not in u or " " in u:
            return ""
        u = "https://" + u
    host = urlparse(u).netloc.lower()
    if any(host == s or host.endswith("." + s) for s in SOCIAL):
        return ""
    return u


def host_matches(host, domains):
    return any(host == d or host.endswith("." + d) for d in domains)


# ---------------------------------------------------------------- classification
def classify(hosts, frames, html):
    ev = {}

    def add(p, s, why):
        ev.setdefault(p, []).append((s, why))

    frame_hosts = [urlparse(f).netloc.lower() for f in frames if f]
    for p, sig in SIGS.items():
        only_frames = sig.get("frame_only", False)
        for fh in frame_hosts:
            if host_matches(fh, sig["hosts"]):
                add(p, STRONG, "iframe:" + fh)
        if only_frames:
            continue
        for h in hosts:
            if host_matches(h, sig["hosts"]):
                add(p, STRONG, "request:" + h)
        for rx in sig["html"]:
            m = re.search(rx, html or "", re.I)
            if m:
                add(p, MED, "html:" + m.group(0)[:40])
    if not ev:
        return "Unidentified", "none", []
    ranked = sorted(ev.items(), key=lambda kv: (max(s for s, _ in kv[1]), len(kv[1])), reverse=True)
    best, items = ranked[0]
    top = max(s for s, _ in items)
    conf = {STRONG: "high", MED: "medium", WEAK: "low"}[top]
    evidence = sorted({w for _, w in items})[:6]
    others = [p for p, _ in ranked[1:3]]
    if others:
        evidence.append("also:" + ",".join(others))
    return best, conf, evidence


def other_hosts(hosts, first_party):
    fp = ".".join(first_party.split(".")[-2:]) if first_party else ""
    out = Counter()
    for h in hosts:
        if not h or (fp and h.endswith(fp)) or any(n in h for n in NOISE):
            continue
        out[h] += 1
    return [h for h, _ in out.most_common(8)]


# ---------------------------------------------------------------- browser helpers
def dismiss_age_gate(page):
    pat = re.compile(r"(yes|i am 21|i'm 21|21\+|over 21|of age|enter|confirm|agree|i am of)", re.I)
    for role in ("button", "link"):
        try:
            page.get_by_role(role, name=pat).first.click(timeout=1200)
            page.wait_for_timeout(1000)
            return
        except Exception:
            pass


def visit(ctx, url, acc, timeout=30000):
    """Load one page, merge what it requested/embedded into acc, return candidate menu links."""
    page = ctx.new_page()
    links = []

    def on_req(r):
        try:
            u = urlparse(r.url)
            acc["hosts"].add(u.netloc.lower())
            host = u.netloc.lower()
            if r.resource_type in ("xhr", "fetch") and len(acc["api"]) < 40 and not any(n in host for n in NOISE):
                acc["api"].add((host + u.path)[:120])
        except Exception:
            pass

    page.on("request", on_req)
    try:
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            acc["status"] = resp.status if resp else None
            acc.setdefault("visited", []).append([url[:110], acc["status"]])
        except Exception as e:
            acc["errors"].append("goto:" + str(e)[:80])
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        dismiss_age_gate(page)
        page.wait_for_timeout(1500)
        acc["final_url"] = page.url
        html = page.content()
        acc["html"] += html[:400000]
        for f in page.frames:
            if f != page.main_frame and f.url and f.url != "about:blank":
                acc["frames"].append(f.url)
        try:
            links = page.eval_on_selector_all(
                "a[href]", "els => els.map(e => ({href: e.href, text: (e.innerText||'').trim().slice(0,60)}))")
        except Exception:
            links = []
    finally:
        page.close()
    return links


GUESS_PATHS = ["/menu", "/shop", "/order", "/order-online", "/online-menu", "/products", "/store", "/shop-now"]


def pick_menu_links(links, base, n=2, town=""):
    base_host = urlparse(base).netloc.lower()
    want = re.compile(r"(shop|menu|order|products|store)", re.I)
    words = [w for w in re.findall(r"[a-z]+", town.lower()) if len(w) > 3 and w not in ("township", "borough")]
    town_rx = re.compile("|".join(re.escape(w) for w in words), re.I) if words else None
    seen, out = set(), []
    for l in links:
        href = l.get("href", "")
        if not href.startswith("http") or href.rstrip("/") == base.rstrip("/"):
            continue
        host = urlparse(href).netloc.lower()
        if host_matches(host, SOCIAL) or any(x in host for x in ("google", "apple.com", "alpineiq")):
            continue
        path = urlparse(href).path
        text = l.get("text", "")
        hit = want.search(text) or want.search(path) or (town_rx and (town_rx.search(path) or town_rx.search(text)))
        if hit:
            key = href.split("#")[0]
            if key not in seen:
                seen.add(key)
                out.append(key)
    out.sort(key=lambda h: 0 if urlparse(h).netloc.lower() == base_host else 1)
    return out[:n]


# ---------------------------------------------------------------- discover
def walk(obj, out):
    if isinstance(obj, dict):
        name = first(obj, ["name", "title", "business_name", "label", "dba"])
        has_geo = any(k.lower() in ("lat", "latitude", "lng", "longitude") for k in obj)
        addr = first(obj, ["address", "formatted_address", "full_address", "street", "street_address"])
        if name and (has_geo or addr):
            out.append({
                "name": name,
                "address": addr,
                "town": first(obj, ["city", "town", "locality"]),
                "county": first(obj, ["county"]),
                "website": norm_url(first(obj, ["website", "web", "site", "url", "link", "website_url"])),
            })
        for v in obj.values():
            walk(v, out)
    elif isinstance(obj, list):
        for v in obj:
            walk(v, out)


def cmd_discover(args):
    from playwright.sync_api import sync_playwright
    RAW.mkdir(exist_ok=True)
    caps = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)
        ctx = browser.new_context(user_agent=UA, viewport={"width": 1400, "height": 950})
        page = ctx.new_page()

        def on_resp(r):
            try:
                ct = (r.headers.get("content-type") or "").lower()
                if "json" in ct and r.status == 200:
                    body = r.text()
                    caps.append({"url": r.url, "bytes": len(body), "body": body})
            except Exception:
                pass

        page.on("response", on_resp)
        print("Loading", args.map_url)
        try:
            page.goto(args.map_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_load_state("networkidle", timeout=30000)
        except Exception as e:
            print("  note:", str(e)[:120])
        page.wait_for_timeout(5000)
        for _ in range(6):  # nudge lazy loading
            page.mouse.wheel(0, 1200)
            page.wait_for_timeout(800)
        (RAW / "map_page.html").write_text(page.content(), encoding="utf-8")
        (RAW / "map_text.txt").write_text(page.inner_text("body"), encoding="utf-8", errors="ignore")
        page.screenshot(path=str(RAW / "map.png"))
        try:
            page.goto(FIND_URL, wait_until="domcontentloaded", timeout=45000)
            (RAW / "find_page.txt").write_text(page.inner_text("body"), encoding="utf-8", errors="ignore")
        except Exception:
            pass
        browser.close()

    cands = []
    for i, c in enumerate(caps):
        (RAW / f"capture_{i:03d}.json").write_text(
            json.dumps({"url": c["url"], "body": c["body"]}), encoding="utf-8")
        try:
            walk(json.loads(c["body"]), cands)
        except Exception:
            pass
    seen, rows = set(), []
    for c in cands:
        k = slug(c["name"] + " " + c["address"])
        if k not in seen:
            seen.add(k)
            rows.append(c)
    with CANDIDATES.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["name", "address", "town", "county", "website"])
        w.writeheader()
        w.writerows(rows)
    print(f"Captured {len(caps)} JSON responses -> raw/capture_*.json")
    print(f"Wrote {len(rows)} candidate stores -> {CANDIDATES.name} "
          f"({sum(1 for r in rows if r['website'])} with a website)")
    print("Next: tell Claude the discover step finished (it will check the captures and build stores.csv).")


# ---------------------------------------------------------------- detect
def load_stores():
    if not STORES.exists():
        sys.exit("stores.csv not found. Run discover first, then have Claude build stores.csv from the candidates.")
    rows = []
    with STORES.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            r["id"] = r.get("id") or slug(f"{r.get('name','')} {r.get('town','')}")
            rows.append(r)
    return rows


def done_ids(redo=()):
    latest = {}
    if RESULTS.exists():
        for line in RESULTS.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                latest[r["id"]] = r.get("platform", "")
            except Exception:
                pass
    return {i for i, p in latest.items() if p not in redo}


def scan_store(ctx, s):
    url = norm_url(s.get("website", ""))
    town = s.get("town", "")
    res = {"id": s["id"], "name": s.get("name", ""), "town": town, "county": s.get("county", ""),
           "website": url, "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if not url:
        res.update(platform="No website", confidence="none", evidence=[], menu_url="", api_endpoints=[],
                   other_hosts=[], error="")
        return res
    acc = {"hosts": set(), "frames": [], "html": "", "api": set(), "errors": [], "final_url": url, "status": None}
    links = visit(ctx, url, acc)
    visited = {acc["final_url"].rstrip("/")}
    all_links = list(links)
    menu_url = acc["final_url"]
    for ml in pick_menu_links(links, acc["final_url"], town=town):
        if ml.rstrip("/") in visited:
            continue
        visited.add(ml.rstrip("/"))
        all_links += visit(ctx, ml, acc)
        menu_url = ml
    platform, conf, evidence = classify(acc["hosts"], acc["frames"], acc["html"])
    if platform == "Unidentified":  # second pass: common menu paths, sister sites, menu subdomains, town links
        base = urlparse(acc["final_url"])
        origin = f"{base.scheme}://{base.netloc}"
        base_host = base.netloc.lower()
        reg = ".".join(base_host.split(".")[-2:])
        stem = reg.split(".")[0]
        sister = []
        for l in all_links:
            h = urlparse(l.get("href", "")).netloc.lower()
            if h and h != base_host and len(stem) > 4 and stem in h and not host_matches(h, SOCIAL):
                sister.append(l["href"].split("#")[0])
        subs = [f"https://{h}/" for h in sorted(acc["hosts"])
                if h.endswith("." + reg) and h.split(".")[0] in ("menu", "shop", "order", "store", "ecomm", "online", "app")]
        tries = ([origin + p for p in GUESS_PATHS[:4]] + sister[:2] + subs[:2]
                 + pick_menu_links(all_links, acc["final_url"], n=3, town=town) + [origin + p for p in GUESS_PATHS[4:]])
        tried = 0
        for t in tries:
            if t.rstrip("/") in visited:
                continue
            visited.add(t.rstrip("/"))
            acc["status"] = None
            all_links += visit(ctx, t, acc)
            tried += 1
            platform, conf, evidence = classify(acc["hosts"], acc["frames"], acc["html"])
            if platform != "Unidentified":
                menu_url = t
                evidence = list(evidence) + ["found-via:" + urlparse(t).netloc[:30] + urlparse(t).path[:20]]
                break
            if tried >= 8:
                break
    fp = urlparse(acc["final_url"]).netloc.lower()
    res.update(platform=platform, confidence=conf, evidence=evidence, menu_url=menu_url,
               api_endpoints=sorted(acc["api"])[:15], other_hosts=other_hosts(acc["hosts"], fp),
               all_hosts=sorted(h for h in acc["hosts"] if h)[:60], frames=sorted(set(acc["frames"]))[:10],
               visited=acc.get("visited", [])[:14],
               error="; ".join(acc["errors"])[:200])
    return res


def cmd_detect(args):
    from playwright.sync_api import sync_playwright
    stores = load_stores()
    if args.shard:
        i, n = (int(x) for x in args.shard.split("/"))
        stores = [s for k, s in enumerate(stores) if k % n == i - 1]
    finished = done_ids(set(x.strip() for x in args.redo.split(",") if x.strip()))
    todo = [s for s in stores if s["id"] not in finished]
    if args.limit:
        todo = todo[:args.limit]
    cache = {}
    print(f"{len(stores)} stores in scope, {len(finished)} already done, {len(todo)} to scan")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed, args=["--disable-http2"])
        ctx = browser.new_context(user_agent=UA, viewport={"width": 1366, "height": 900}, locale="en-US")
        for k, s in enumerate(todo, 1):
            try:
                key = norm_url(s.get("website", ""))
                if key and key in cache:  # same URL as an earlier store (chains): reuse, don't reload
                    res = dict(cache[key])
                    res.update(id=s["id"], name=s.get("name", ""), town=s.get("town", ""), county=s.get("county", ""),
                               checked_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
                    res["evidence"] = list(res.get("evidence", [])) + ["reused:same-url"]
                    reused = True
                else:
                    res = scan_store(ctx, s)
                    reused = False
                    if key:
                        cache[key] = res
            except KeyboardInterrupt:
                print("Stopped. Run the same command again to resume.")
                break
            except Exception as e:
                reused = False
                res = {"id": s["id"], "name": s.get("name", ""), "town": s.get("town", ""), "website": s.get("website", ""),
                       "platform": "Error", "confidence": "none", "evidence": [], "menu_url": "",
                       "api_endpoints": [], "other_hosts": [], "error": str(e)[:200],
                       "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            with RESULTS.open("a", encoding="utf-8") as f:
                f.write(json.dumps(res) + "\n")
            print(f"[{k}/{len(todo)}] {res['name'][:34]:34} -> {res['platform']} ({res['confidence']})")
            if k % 25 == 0:  # fresh context now and then to keep memory flat
                ctx.close()
                ctx = browser.new_context(user_agent=UA, viewport={"width": 1366, "height": 900}, locale="en-US")
            if not reused:
                time.sleep(args.delay + random.random() * args.delay)
        browser.close()


# ---------------------------------------------------------------- summary
def cmd_summary(args):
    if not RESULTS.exists():
        sys.exit("No results.jsonl yet.")
    latest = {}
    for line in RESULTS.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
            latest[r["id"]] = r
        except Exception:
            pass
    rows = list(latest.values())
    changed = 0
    for r in rows:
        if r.get("platform") in ("Unidentified",) and r.get("all_hosts"):
            plat, conf, ev = classify(set(r["all_hosts"]), r.get("frames", []), "")
            if plat != "Unidentified":
                r["platform"], r["confidence"], r["evidence"] = plat, conf, list(ev) + ["reclassified-from-hosts"]
                changed += 1
    if changed:
        print(f"Re-classified {changed} stores from saved host lists")
    cols = ["name", "town", "county", "website", "menu_url", "platform", "confidence", "evidence",
            "api_endpoints", "other_hosts", "error", "checked_at"]
    with (HERE / "results.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([";".join(r[c]) if isinstance(r.get(c), list) else r.get(c, "") for c in cols])
    counts = Counter(r["platform"] for r in rows)
    print(f"{len(rows)} stores scanned")
    for p, n in counts.most_common():
        print(f"  {n:4}  {p}")
    print("Wrote results.csv")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("discover")
    d.add_argument("--map-url", default=MAP_URL)
    d.add_argument("--headed", action="store_true", help="show the browser window")
    d.set_defaults(fn=cmd_discover)
    t = sub.add_parser("detect")
    t.add_argument("--limit", type=int, default=0, help="only scan this many stores (good for a first test)")
    t.add_argument("--shard", help="e.g. 1/3 to split the list across several terminal windows")
    t.add_argument("--delay", type=float, default=1.5, help="base seconds to wait between stores")
    t.add_argument("--headed", action="store_true")
    t.add_argument("--redo", default="", help='rescan stores whose last result was one of these, e.g. "Unidentified,Error"')
    t.set_defaults(fn=cmd_detect)
    s = sub.add_parser("summary")
    s.set_defaults(fn=cmd_summary)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
