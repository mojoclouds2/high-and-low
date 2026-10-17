#!/usr/bin/env bash
# High & Low: pull fresh prices, then upload the page to GoDaddy hosting (upload.sh).
# Run by hand, or hourly from cron (see README). Linux counterpart of refresh.bat.
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

echo "[$(date)] refresh started" >> refresh.log
if ! .venv/bin/python scrape.py >> refresh.log 2>&1; then
  echo "[$(date)] scrape failed, NOT deploying" >> refresh.log
  exit 1
fi
if ! ./upload.sh >> refresh.log 2>&1; then
  echo "[$(date)] upload to GoDaddy failed" >> refresh.log
  exit 1
fi
echo "[$(date)] refresh done" >> refresh.log
