"""Spot-check product deep links: for each store, open two product links in a browser and see whether the page mentions the product.
Usage: python tools/check_links.py <site/data folder> [store ids...]     (a missing id list checks every store file in the folder)
Prints OK / WEAK (page loaded but product name not found: link may only open the menu) / FAIL (didn't load)."""
import json, re, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

data = Path(sys.argv[1])
ids = sys.argv[2:] or sorted(p.name[:-5] for p in data.glob("*.json") if not re.search(r"\.d\.json|brands|zips", p.name))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"
words = lambda n: [w for w in re.findall(r"[a-z0-9]{4,}", n.lower())][:3]
with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
    ctx = b.new_context(user_agent=UA, viewport={"width": 1366, "height": 900})
    for sid in ids:
        rows = [r for r in json.loads((data / f"{sid}.json").read_text())["rows"] if r.get("url")]
        step = max(1, len(rows) // 3)
        res = []
        for r in rows[step::step][:2] or rows[:1]:
            page = ctx.new_page()
            try:
                page.goto(r["url"], wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(5000)
                for label in ("I am 21 or older", "Yes", "I'm 21", "Enter"):
                    try:
                        page.get_by_role("button", name=label).first.click(timeout=800); page.wait_for_timeout(1500); break
                    except Exception:
                        pass
                text = " ".join(f.inner_text("body").lower() for f in page.frames if f.url != "about:blank" and True) if False else page.inner_text("body").lower()
                for f in page.frames[1:]:
                    try: text += " " + f.locator("body").inner_text(timeout=1500).lower()
                    except Exception: pass
                res.append("OK" if all(w in text for w in words(r["name"])) else "WEAK")
            except Exception:
                res.append("FAIL")
            finally:
                page.close()
        print(f"{sid:48} {'/'.join(res)}   e.g. {rows[0]['url'][:90]}", flush=True)
    b.close()
