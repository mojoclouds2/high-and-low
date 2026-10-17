# High & Low

**Buy low.  Get high.** South Jersey's best dispensary prices, all in one place.

A static website that compares prices across dispensary menus. A Python scraper (run on your PC)
pulls every store's menu, builds one page (`site/index.html`), and publishes it to Vercel.

This copy covers **Daylite, Nirvana, Sage and NAR** (Mount Laurel). Gynsyng, Brotherly Bud, Enlighten
and Quality Roots are in the code but switched off (see "Turning stores on or off").

---

## How it works

```
your PC (hourly)                                   Vercel
python scrape.py  ->  site/index.html  ->  vercel deploy  ->  your public URL
```

- Vercel only hosts the finished page. It does **not** run the scraper (the scraper needs a real
  browser, which Vercel's servers don't provide).
- `refresh.bat` does both steps: scrape, then deploy. Task Scheduler runs it every hour.
- If every store fails, nothing is deployed and the live site keeps its last good version.
  If one store fails, the others update and that store keeps its last prices, marked "stale".

---

## Ship it (first time, about 20 minutes)

### 1. Install the tools (once)

- **Python 3.10 or newer**: https://www.python.org/downloads/ (check "Add python.exe to PATH" in the installer)
- **Node.js LTS** (needed for the Vercel command-line tool): https://nodejs.org/

Then open a terminal (PowerShell) **in this folder** and run:

```
pip install -r requirements.txt
python -m playwright install chromium
npm install -g vercel
vercel login
```

### 2. Get fresh prices — do this before deploying

The page included in `site/` was built from data captured on **Sept 29, 2026**, so its prices are old.

```
python scrape.py
```

It takes about 2–3 minutes and prints one line per store, e.g.
`sage {'ok': True, 'count': 416}`. Then open `site\index.html` in your browser to check it.

If a store shows `'ok': False`, the run still finishes; that store keeps its Sept 29 prices and is
marked "stale" on the page. Send the error text to whoever maintains the code.

### 3. Deploy to Vercel

```
vercel deploy --prod --cwd site
```

The first time, it asks a few questions:

| Question | Answer |
|---|---|
| Set up and deploy? | `Y` |
| Which scope? | your account |
| Link to existing project? | `N` |
| Project name? | `high-and-low` (or anything) |
| In which directory is your code located? | `./` |
| Want to modify these settings? | `N` |

It prints your live URL (e.g. `https://high-and-low.vercel.app`). After that first run, the same
command redeploys without questions.

### 4. Custom domain (optional)

Vercel dashboard → your project → **Settings → Domains** → add your domain and follow the DNS steps.

### 5. Refresh every hour (Windows Task Scheduler)

1. Open **Task Scheduler** → **Create Task…** (not "Basic Task").
2. **General:** name it `High & Low refresh`; choose "Run only when user is logged on".
3. **Triggers → New:** Daily, start now; check **Repeat task every: 1 hour**, for a duration of **Indefinitely**.
4. **Actions → New:** Program/script: the full path to `refresh.bat` in this folder.
   **Start in:** this folder's full path (for example `C:\Users\you\high-and-low`).
5. **Settings:** check "Run task as soon as possible after a scheduled start is missed".

Each run appends to `refresh.log` in this folder. Your PC must be on and awake for refreshes to happen.

---

## What's in this folder

| Path | What it is |
|---|---|
| `site/` | **The website** — what gets deployed. `index.html` (page + data), `favicon.png`, `vercel.json` (cache headers) |
| `scrape.py` | Pulls each store's menu and rebuilds `site/index.html` |
| `normalize.py` | Store list and settings, categories, sizes, $/gram, matching the same product across stores |
| `template.html` | The page design. Data is inserted at build time — edit this, not `site/index.html` |
| `refresh.bat` | Scrape + deploy in one step (used by Task Scheduler) |
| `build_snapshot.py` | Rebuilds the page from `data/` without scraping — handy after editing `template.html` |
| `data/` | Saved store data from Sept 29, 2026 (used by `build_snapshot.py`) |
| `out/products.json` | Last run's data, kept private; used as the fallback when a store fails |
| `logo.png` | The mascot logo (also built into the page and used as the favicon) |
| `requirements.txt` | Python packages |

Only `site/` goes to Vercel. The code, data and logs stay on your PC.

---

## How each store is read

| Store | Menu system | Method |
|---|---|---|
| Sage | Flowhub | The menu's own page-data JSON, 20 products per page |
| NAR | Dutchie | Opens one Dutchie menu to copy its product queries, then runs them with NAR's store id |
| Daylite, Nirvana | Dispense | Types in the menu's search box so it requests products, then pages through the whole menu with that request's headers |
| *(off)* Gynsyng, Brotherly Bud, Enlighten | Dutchie | Same as NAR |
| *(off)* Quality Roots | Own API | `api.getqualityroots.com/products/`, 100 per page |

No keys or passwords are stored in the code; anything a menu needs is read from the live page each run.

## Turning stores on or off

In `normalize.py`, each store in `STORES` has `"enabled": True` or `False`. Change it, run
`python scrape.py` (or `refresh.bat`), and the site updates. To add another Dutchie store, add one line
to `DUTCHIE` in `scrape.py` (its dispensary id and product link) and one to `STORES`.

## Medical menus

None of these stores sells to medical patients online (checked Sept 2026), so the site shows
recreational prices and the Rec / Med / Both switch stays hidden. If a store adds a medical menu,
set `"medical": True` for it in `STORES`; the switch and the green-cross MEDICAL badge then appear
automatically (Dutchie and Flowhub stores work as-is; for Dispense stores also put the medical
menu's site in `DISPENSE_MED` in `scrape.py`).

## Site features

- 21+ age check on first visit (remembered on that device)
- Search, category and size filters, Indica/Sativa/Hybrid, on sale, "at 2+ stores"
- Sort by price, $/gram, THC, biggest price gap
- Tap a store button to hide/show that store; a note above the buttons explains it
- Tap a row for the product description, cannabinoids, terpenes, effects, stock and brand info
- Tap a product name or price to open it on the store's own site

---

## Troubleshooting

- **`python` or `vercel` "not recognized"** — reinstall Python with "Add to PATH" checked / reinstall
  Node.js, then open a new terminal.
- **A store shows "stale"** — its menu couldn't be read this run. It usually clears on the next run.
  If it stays stale for a day, the store probably changed its website and that connector needs updating.
- **`Every store failed this run; not safe to deploy.`** — usually no internet, or the PC was asleep.
  The live site is untouched.
- **Deploy asks to log in again** — run `vercel login` in a terminal.
- **Changed the design** — edit `template.html`, run `python build_snapshot.py` to preview with saved
  data, then `refresh.bat` (or `vercel deploy --prod --cwd site`) to publish.

## Deploying from GitHub instead (optional)

If you'd rather use a Git repo: push this folder to GitHub, import it in Vercel, and in the project
settings set **Root Directory** to `site`, **Framework Preset** to "Other", and leave the build command
empty. Then replace the `vercel deploy` line in `refresh.bat` with:

```
git add site && git commit -m "Refresh prices" && git push
```

---

## Before you go public

- The site says it's independent and not affiliated with any dispensary, and asks visitors to confirm
  prices at checkout. Keep that wording.
- Each store's prices come from its public online menu. Review each store's website terms, and stop
  listing any store that asks you to.
- Check Vercel's Acceptable Use Policy for cannabis-related content before relying on it long term.
