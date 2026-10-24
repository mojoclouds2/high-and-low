"""Fill in each new store's scraper settings in stores.json by loading its public menu page like a visitor would.

  Dutchie  -> adapter.id (the dispensary id seen in the menu's own product request), adapter.link (product deep-link template)
  Dispense -> adapter.base (menu site) after confirming the menu asks api.dispenseapp.com for products

Usage:  python tools/discover_stores.py --wave 1 --shard 1/4 --out DIR   discover one quarter of a wave; run the shards in parallel
        python tools/discover_stores.py --merge DIR                    apply every shard's findings to stores.json
        python tools/discover_stores.py --wave 1                       single process, writes stores.json directly
        python tools/discover_stores.py --ids a,b --force   redo specific stores (also re-checks stores that already have settings)
        python tools/discover_stores.py --ids enlighten --dry-run    print findings, don't write stores.json
Loads one page set per store, with a pause between stores. Results go into stores.json; review the diff before enabling a store."""
import argparse, json, re, sys, time
from pathlib import Path
from urllib.parse import urlparse, parse_qs, quote

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import scrape  # reuse the production Dutchie helpers so discovery tests ids the same way the scraper will

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "stores.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36")
GATE = re.compile(r"(yes|i am 21|i'm 21|21\+|over 21|of age|enter|confirm|agree|i am of)", re.I)
HEX24 = re.compile(r"\b[0-9a-f]{24}\b")


def pass_gate(page):
    for role in ("button", "link"):
        try:
            page.get_by_role(role, name=GATE).first.click(timeout=1500)
            page.wait_for_timeout(1200)
            return
        except Exception:
            pass


def candidates(s):
    """Pages to try, most likely first: the scan's menu URL, the website, then common menu paths."""
    out = []
    for u in (s.get("url"), s.get("website")):
        if u and u not in out:
            out.append(u)
    site = s.get("website") or s.get("url") or ""
    if site:
        o = urlparse(site if "://" in site else "https://" + site)
        for p in ("/menu", "/shop", "/order-online"):
            u = f"{o.scheme}://{o.netloc}{p}"
            if u not in out:
                out.append(u)
    return out[:3]


def load(ctx, url, seen, wait=9000):
    page = ctx.new_page()
    page.on("request", lambda r: seen.append(r.url))
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        page.wait_for_timeout(2500)
        pass_gate(page)
        for _ in range(3):
            page.mouse.wheel(0, 1800)
            page.wait_for_timeout(1200)
        page.wait_for_timeout(wait)
        frames = [f.url for f in page.frames if f.url and f.url != "about:blank"]
        final = page.url
    except Exception as e:
        frames, final = [], f"error: {str(e)[:80]}"
    finally:
        page.close()
    return frames, final


def product_count(ctx, did):
    """How many products Dutchie returns for this dispensary id (0 = not a real id). Same query the scraper uses."""
    Q = scrape._dutchie_queries(ctx)
    lu, lqs, lvars = Q["list"]
    v = json.loads(json.dumps(lvars)); v["productsFilter"]["dispensaryId"] = did; v["productsFilter"]["pricingType"] = "rec"; v["perPage"] = 100; v["page"] = 0
    try:
        j = scrape._gql(Q["page"], scrape._with_vars(lu, lqs, v))
        return len(((j.get("data") or {}).get("filteredProducts") or {}).get("products") or [])
    except Exception:
        return 0


def ids_from_urls(urls):
    ids = []
    for u in urls:
        if "operationName=FilteredProducts" in u or "operationName=IndividualFilteredProduct" in u:
            try:
                v = json.loads(parse_qs(urlparse(u).query).get("variables", ["{}"])[0])
                i = (v.get("productsFilter") or {}).get("dispensaryId")
                if i:
                    ids.append(i)
            except Exception:
                pass
        m = re.search(r"embedded-menu/([0-9a-f]{24})", u)
        if m:
            ids.append(m.group(1))
    return ids


def find_dutchie(ctx, s):
    for url in candidates(s):
        seen = []
        page = ctx.new_page()
        page.on("request", lambda r: seen.append(r.url))
        html = ""
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(2500); pass_gate(page)
            for _ in range(3):
                page.mouse.wheel(0, 1800); page.wait_for_timeout(1200)
            page.wait_for_timeout(6000)
            frames = [f.url for f in page.frames if f.url and f.url != "about:blank"]
            final = page.url
            html = page.content()
        except Exception as e:
            frames, final = [], f"error: {str(e)[:80]}"
        finally:
            page.close()
        slug, kind = None, None
        for f in frames + seen:
            m = re.search(r"dutchie\.com/(?:embedded-menu|dispensary)/([a-z][a-z0-9-]+)", f)
            if m:
                slug = slug or m.group(1); kind = "iframe" if "embedded-menu" in f else (kind or "dutchie-site")
        if any(re.search(r"dutchie\.com/api/v2/embedded-menu/[0-9a-f]{24}\.js", u) for u in seen):
            kind = kind or "script"
        cands = ids_from_urls(seen)
        if slug and not cands:  # open Dutchie's own page for this store and read the id from its product request
            seen2 = []
            p2 = ctx.new_page(); p2.on("request", lambda r: seen2.append(r.url))
            try:
                p2.goto(f"https://dutchie.com/embedded-menu/{slug}/products/flower", wait_until="domcontentloaded", timeout=25000)
                p2.wait_for_timeout(8000)
            except Exception:
                pass
            finally:
                p2.close()
            cands = ids_from_urls(seen2)
        for m in re.finditer(r"dispensaryId[\"':\s=]+([0-9a-f]{24})", html):
            cands.append(m.group(1))
        if not cands:  # last resort: every 24-hex string on the page; the product check below weeds out the rest
            cands = list(dict.fromkeys(HEX24.findall(html)))[:25]
        for did in dict.fromkeys(cands):
            n = product_count(ctx, did)
            if n:
                return {"id": did, "slug": slug, "kind": kind or "unknown", "found_on": final[:140], "products_first_page": n}
    return None


def find_dispense(ctx, s):
    """Dispense menus live at /menu/... on some sites and /shop/... on others; try the store's own menu URL, then both."""
    for url in candidates(s):
        o = urlparse(url if "://" in url else "https://" + url)
        base = f"{o.scheme}://{o.netloc}"
        paths = [o.path or "/"] if "dispense" not in (o.path or "") else [o.path]
        paths = list(dict.fromkeys(paths + ["/menu/categories/flower", "/shop/categories/flower", "/shop", "/menu"]))
        for path in paths[:4]:
            seen = []
            page = ctx.new_page()
            page.on("request", lambda r: seen.append(r.url))
            try:
                page.goto(base + path, wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(2500)
                pass_gate(page)
                try:
                    box = page.get_by_placeholder("Search products").first
                    box.click(timeout=3000); box.type("blue", delay=60)
                except Exception:
                    pass
                for _ in range(5):
                    if any("api.dispenseapp.com" in u and "/products" in u for u in seen):
                        break
                    page.mouse.wheel(0, 3000); page.wait_for_timeout(1200)
            except Exception:
                pass
            finally:
                page.close()
            hit = next((u for u in seen if "api.dispenseapp.com" in u and "/products" in u), None)
            if hit:
                return {"base": base, "menu_path": path if path != "/" else "/menu/categories/flower",
                        "venue": hit.split("/venues/")[1].split("/")[0] if "/venues/" in hit else None}
    return None


def link_template(s, found):
    """Product deep link: prefer the store's own embed, else Dutchie's own pages, else just the menu page."""
    kind, slug = found.get("kind"), found.get("slug")
    page = (found.get("found_on") or s.get("url") or "").split("?")[0].split("#")[0]
    if kind == "iframe" and slug:
        return f"https://dutchie.com/embedded-menu/{slug}/product/{{c}}"
    if kind == "dutchie-site" and slug:
        return f"https://dutchie.com/dispensary/{slug}/product/{{c}}"
    m = re.match(r"^(https?://[^/]+/stores/[^/]+)(?:/products.*|/?)$", page)
    if m and m.group(1).rsplit("/", 1)[-1] != "products":  # Dutchie white-label store site: product pages sit beside /products
        return m.group(1) + "/product/{c}"
    if kind == "script" and page.startswith("http"):
        return page + "?dtche%5Bproduct%5D={c}"
    return page or s.get("url") or ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wave", type=int); ap.add_argument("--ids"); ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--shard"); ap.add_argument("--out"); ap.add_argument("--merge")
    a = ap.parse_args()
    reg = json.loads(REG.read_text(encoding="utf-8"))
    if a.merge:
        n = 0
        for f in sorted(Path(a.merge).glob("shard-*.json")):
            for sid, patch in json.loads(f.read_text(encoding="utf-8")).items():
                reg[sid]["adapter"].pop("discovery_failed", None); reg[sid]["adapter"].update(patch); n += 1
        REG.write_text(json.dumps(reg, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        return print(f"merged {n} stores into stores.json")
    ids = [i.strip() for i in a.ids.split(",")] if a.ids else [k for k, v in reg.items() if v["wave"] == a.wave]
    todo = [i for i in ids if i in reg and reg[i]["adapter"].get("type") in ("dutchie", "dispense")
            and (a.force or not (reg[i]["adapter"].get("id") or reg[i]["adapter"].get("base")))]
    if a.shard:
        i, n = (int(x) for x in a.shard.split("/")); todo = [t for k, t in enumerate(todo) if k % n == i - 1]
    patches = {}
    shard_file = Path(a.out) / f"shard-{a.shard.replace('/', 'of')}.json" if (a.shard and a.out) else None
    print(f"{len(todo)} stores to discover", flush=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(user_agent=UA, viewport={"width": 1366, "height": 900}, locale="en-US")
        for n, sid in enumerate(todo, 1):
            s = reg[sid]; typ = s["adapter"]["type"]
            try:
                found = find_dutchie(ctx, s) if typ == "dutchie" else find_dispense(ctx, s)
            except Exception as e:
                found = None; print("  error:", str(e)[:100])
            if found and typ == "dutchie":
                patch = dict(id=found["id"], link=link_template(s, found), slug=found.get("slug"), embed=found["kind"])
            elif found:
                patch = dict(base=found["base"], menu_path=found["menu_path"], venue=found.get("venue"))
            else:
                patch = dict(discovery_failed=True)
            if not patch.get("discovery_failed"):
                s["adapter"].pop("discovery_failed", None)
            s["adapter"].update(patch); patches[sid] = patch
            print(f"[{n}/{len(todo)}] {sid:42} {typ:9} -> {found}", flush=True)
            if shard_file and not a.dry_run:
                shard_file.parent.mkdir(parents=True, exist_ok=True); shard_file.write_text(json.dumps(patches, indent=1), encoding="utf-8")
            elif not a.dry_run and not a.shard:
                REG.write_text(json.dumps(reg, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
            time.sleep(a.delay)
        browser.close()


if __name__ == "__main__":
    main()
