#!/usr/bin/env bash
# High & Low: pull fresh prices, then publish by pushing to main (GitHub Pages deploys site/).
# Run by hand, or every 12 hours from cron (see README). Linux counterpart of refresh.bat.
cd "$(dirname "$0")" || exit 1
export PATH="$HOME/.local/opt/node/bin:$HOME/.local/bin:$PATH"

# Sage needs a headed browser, so cron jobs borrow the logged-in desktop session.
export DISPLAY="${DISPLAY:-:0}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
if [ -z "$XAUTHORITY" ]; then
  XAUTHORITY="$(ls -t "$XDG_RUNTIME_DIR"/.mutter-Xwaylandauth.* 2>/dev/null | head -1)"
  export XAUTHORITY
fi

# skip this run if the previous one is still going
exec 9>refresh.lock
flock -n 9 || { echo "[$(date)] previous refresh still running, skipped" >> refresh.log; exit 0; }

# Prices live on their own branch ("data"), replaced with a single commit each run so git history doesn't grow.
# The Pages workflow (pages.yml) merges it with site/ when it deploys. DATA_REMOTE overrides the push target (for tests).
publish_data() {
  local tmp remote
  tmp="$(mktemp -d)"
  remote="${DATA_REMOTE:-$(git remote get-url mojoclouds2)}"
  cp -r site/data/. "$tmp"/ || return 1
  git -C "$tmp" init -q -b data \
    && git -C "$tmp" add -A \
    && git -C "$tmp" -c user.name="$(git config user.name)" -c user.email="$(git config user.email)" commit -q -m "Prices $(date '+%Y-%m-%d %H:%M')" \
    && git -C "$tmp" push -q -f "$remote" data
  local rc=$?
  rm -rf "$tmp"
  return $rc
}

echo "[$(date)] refresh started" >> refresh.log
if ! .venv/bin/python scrape.py >> refresh.log 2>&1; then
  echo "[$(date)] scrape failed, NOT deploying" >> refresh.log
  exit 1
fi
if ! publish_data >> refresh.log 2>&1; then  # data first: the deploy triggered by the main push below then sees fresh prices
  echo "[$(date)] publish of price data failed" >> refresh.log
  exit 1
fi
git add site/index.html data/ >> refresh.log 2>&1
if git diff --cached --quiet; then
  echo "[$(date)] no changes to publish" >> refresh.log
elif ! { git commit -q -m "Refresh prices $(date '+%Y-%m-%d %H:%M')" && git push -q mojoclouds2 main; } >> refresh.log 2>&1; then
  echo "[$(date)] publish to GitHub failed" >> refresh.log
  exit 1
fi
echo "[$(date)] refresh done" >> refresh.log
