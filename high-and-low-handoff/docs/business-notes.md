# High & Low: Business Notes (context for dev)

Condensed from the planning conversation. Not required reading for implementation.

## Positioning
High & Low aggregates product prices across competing South Jersey dispensaries (6 stores live). Consumers use it to find the best deal. Making money from the dispensaries themselves is hard because the product exposes their price competition.

## Monetization ladder (in order of effort)
1. **Affiliate links** for accessories (grinders, vapes batteries, storage, papers). Lowest friction, small revenue, usable on day one. This is what the gear strip implements.
2. **Direct vendor advertising**: accessory and brand vendors buy the single Sponsored slot. Needs traffic first.
3. **Selling to dispensaries**: analytics, price-position reports, promoted listings. Highest value but hardest sale; needs data coverage and legal review.

## Affiliate programs
Sign up through a network or directly. Common starting points: Awin, FlexOffers, and direct programs from accessory merchants. Confirm each accepts cannabis-adjacent sites before applying. Keep a spreadsheet of program, commission, cookie window, payout threshold, link-check date.

## "30-day cookie"
When a visitor clicks an affiliate link, the merchant's site stores a tracking cookie for 30 days. If the visitor buys within that window, the sale is credited to you (last click wins: a later click on someone else's link replaces yours). The links themselves do not expire when the cookie does. Each new click starts a fresh 30 days. Maintenance is about checking that links and programs are still active, not refreshing cookies.

## Market data
See `data/nj_dispensary_platforms_summary.md`. Short version: Dutchie 37%, Dispense 17%, Sweed 11% of NJ stores. An earlier assumption that Dutchie + Jane dominate was wrong.

## Not done / possible follow-ups
- Second half (O to Z) of the CRC license cross-check for store-list completeness.
- Cross-check against Leafly / Weedmaps listings.
- Hand-resolve the ~60 unidentified stores.
