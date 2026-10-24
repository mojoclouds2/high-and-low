# highlow-go: click redirect for affiliate and sponsored links

Visitors click `https://<worker>/go/<id>?c=<category>`. The Worker logs the click anonymously and sends a 302 to the
merchant. The page never contains the merchant URL, so links can be swapped without redeploying the site.

Logged per click: time, tile id, category, the page that referred it, country. No IP, cookies or user agent.

## Change a link or add a tile
1. Edit `../affiliates.json` (tile `id`, `url`, and so on; `enabled: false` pauses one).
2. `python ../make_redirects.py` (checks ids and https, writes `redirects.json`).
3. `npm run deploy`, then rebuild the site if tiles were added or removed (`../refresh.sh` does this).
Changing only a link's `url` needs steps 1-3 but no site rebuild.

## First-time setup (about 10 minutes, once)
1. Create a free account at https://dash.cloudflare.com/sign-up.
2. In this folder: `npm install` then `npx wrangler login` (opens a browser to approve).
3. Optional click database:
   - `npx wrangler d1 create highlow-clicks`, paste the printed `database_id` into `wrangler.toml`, uncomment the `[[d1_databases]]` block;
   - `npx wrangler d1 execute highlow-clicks --remote --file=schema.sql`.
   Without D1, clicks are still in the Worker's Logs (Cloudflare dashboard > Workers > highlow-go > Logs), but those expire after a few days.
4. `npm run deploy`. It prints `https://highlow-go.<your-subdomain>.workers.dev`.
5. Put that address plus `/go/` into `go_base` in `../affiliates.json` (e.g. `https://highlow-go.you.workers.dev/go/`).

## Reading clicks
`npx wrangler d1 execute highlow-clicks --remote --command "SELECT id, cat, COUNT(*) n FROM clicks WHERE ts > date('now','-30 day') GROUP BY id, cat ORDER BY n DESC"`

## When the domain is bought
Add the domain to Cloudflare, uncomment `routes` in `wrangler.toml` (for example `go.yourdomain.com/*`), set `SITE_URL` to the site's
address, deploy, and change `go_base` to `https://go.yourdomain.com/go/`. Nothing else changes.

## Test locally
`npx wrangler dev`, then `curl -i localhost:8787/go/<id>`.
