# NJ dispensary menu platforms: what to build first

Scan of the 331 locations on the NJ Cannabis Regulatory Commission dispensary map, October 2026. Full per-store data is in `nj_dispensary_platforms.xlsx` and `.json`.

## The headline

258 of 331 stores (78%) are on an identifiable menu platform. Three platforms cover 215 of them, which is 65% of every store in the state and 83% of the ones identified:

- **Dutchie: 123 stores (37%).** The clear leader, and it can sit under a store that shows a different logo (Brotherly Bud's footer credits LeafBridge, but its menu requests go to Dutchie).
- **Dispense: 55 stores (17%).** Includes Daylite and Nirvana.
- **Sweed: 37 stores (11%).** Includes Zen Leaf, Natural Apothecary and Sanctuary.

Then a long tail: Flowhub 9 (Sage), Jane 7, Herb.co 6, Meadow 4, Blaze 3, Treez 3, Shopify storefronts 3 (including NAR), Proteus420 2, and one each of Carrot, Cova, Hashly, Hytiva, Joint Commerce and a Leafly embed.

## What this means for High & Low

Earlier I guessed that Dutchie plus Jane would cover most of the market. That was wrong: Jane is only 7 stores. A Dutchie adapter alone reaches about a third of New Jersey, adding Dispense and Sweed reaches roughly two thirds, and every adapter after that adds only a handful of stores. Build in this order: Dutchie, Dispense, Sweed, then Flowhub, then decide whether the remaining small vendors are worth a parser each or whether those stores can be skipped.

The `api_paths` field in the JSON lists the data calls the menus make. That is the starting point for each adapter.

## The 60 stores that did not resolve

- 16 failed to load in the browser at all.
- 13 are built on Prismic with no menu vendor visible.
- 12 show no third-party vendor.
- 6 belong to chains with in-house menus (Curaleaf, RISE, Ayr, The Cannabist) that automated tools cannot read.
- 13 are blocked by site protection or return 404 on their menu pages.
- A further 13 stores have no website listed on the state map.

Unidentified does not mean the store has no menu. Many of these can be settled by hand in a few minutes each.

## Caveats

- Six vendors (Herb.co, Hytiva, Proteus420, Carrot, Joint Commerce, Hashly) were named from hostnames alone and are marked medium confidence.
- The store list is the CRC's map, which includes licensed locations that may not be open yet. A partial check against the CRC's license table (businesses A to N only) matched about 86% of licensed locations to a map pin, so some real stores are probably missing. The O to Z half was never checked.
- Platforms change when a store switches vendors. Re-running `py crawl.py detect` refreshes the data.
- Scraping a menu is a separate question from detecting its platform. Each vendor's terms of service still apply, and a vendor or a store can cut off access to its menu, so check those terms before building on any of them.
