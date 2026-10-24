// High & Low click redirect: /go/<id> -> merchant URL, with an anonymous click log.
// The id -> URL table is redirects.json, generated from affiliates.json by make_redirects.py.
// Logged per click: time, tile id, category, referring page, country. No IP, no cookies, no user agent.
import REDIRECTS from "../redirects.json";

const ID_RE = /^[a-z0-9][a-z0-9_-]{0,63}$/;

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const home = env.SITE_URL || "/";

    if (url.pathname === "/robots.txt") {
      return new Response("User-agent: *\nDisallow: /go/\n", { headers: { "content-type": "text/plain" } });
    }
    const m = /^\/go\/([^/]+)\/?$/.exec(url.pathname);
    if (!m || (request.method !== "GET" && request.method !== "HEAD")) return Response.redirect(home, 302);

    let id = "";
    try { id = decodeURIComponent(m[1]).toLowerCase(); } catch (e) {}
    const dest = ID_RE.test(id) ? REDIRECTS[id] : undefined;
    if (!dest) return Response.redirect(home, 302); // unknown or retired link: send the visitor back to the site

    if (request.method === "GET") {
      const ref = request.headers.get("referer") || "";
      let page = "";
      try { page = new URL(ref).pathname.slice(0, 120); } catch (e) {}
      const row = {
        ts: new Date().toISOString(),
        id,
        cat: (url.searchParams.get("c") || "").slice(0, 40),
        page,
        country: (request.cf && request.cf.country) || "",
      };
      console.log(JSON.stringify({ click: row }));
      if (env.DB) {
        ctx.waitUntil(env.DB.prepare("INSERT INTO clicks (ts, id, cat, page, country) VALUES (?, ?, ?, ?, ?)")
          .bind(row.ts, row.id, row.cat, row.page, row.country).run().catch(e => console.log("log failed: " + e)));
      }
    }
    return new Response(null, {
      status: 302,
      headers: { location: dest, "cache-control": "no-store", "x-robots-tag": "noindex, nofollow", "referrer-policy": "no-referrer" },
    });
  },
};
