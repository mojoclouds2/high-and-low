# NJ dispensary menu-platform scan

Finds which online-menu platform (Dutchie, Jane, Dispense, Flowhub, LeafBridge, Shopify, etc.) every licensed NJ dispensary uses.

## One-time setup (Windows PowerShell, inside this folder)

    py -m pip install playwright
    py -m playwright install chromium

## Run it

1. Get the store list from the state's map:

       py crawl.py discover

   Saves what the map loads into `raw\` and writes `stores_candidates.csv`.
   **Stop here and tell Claude it finished.** Claude will check the captures, build `stores.csv`
   (name, town, county, website), and fill in missing websites. The map's data format is the one piece
   that could not be tested ahead of time, so expect one round of fixing here.

2. Quick test on a handful of stores:

       py crawl.py detect --limit 5

3. Full run (about 30-60 minutes for 300+ stores, saves after every store):

       py crawl.py detect

   Ctrl+C stops it; running the same command again resumes where it left off.
   To go faster, open three PowerShell windows and run `--shard 1/3`, `--shard 2/3`, `--shard 3/3`.

4. When it finishes:

       py crawl.py summary

   Writes `results.csv` and prints store counts per platform. Tell Claude it's done and it will build the
   spreadsheet, the short write-up and the JSON for High & Low from `results.jsonl`.

## Notes

- It loads each store's public menu pages the way a visitor would, one at a time, with a pause between stores.
- Each result records the evidence behind the call (hosts requested, iframes, footer credits) and the JSON
  API paths the menu calls, which is what you need to write a scraper adapter.
- `Unidentified` means no known platform signature matched; the result still lists the other hosts the site
  loaded so the platform can usually be worked out by hand.
- `--headed` shows the browser window if you want to watch or debug.
