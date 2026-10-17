#!/usr/bin/env bash
# Upload the finished page to GoDaddy web hosting over SFTP (called by refresh.sh, or run by hand).
# Settings live outside the repo in ~/.config/high-and-low/godaddy.env (see README), e.g.:
#   GD_HOST=sftp.example.com   GD_USER=cpaneluser   GD_DIR=public_html   GD_KEY=~/.ssh/godaddy_highlow
cd "$(dirname "$0")" || exit 1
CONF="$HOME/.config/high-and-low/godaddy.env"
[ -f "$CONF" ] || { echo "upload: missing $CONF" >&2; exit 1; }
# shellcheck source=/dev/null
. "$CONF"
: "${GD_HOST:?set GD_HOST}" "${GD_USER:?set GD_USER}" "${GD_DIR:=public_html}" "${GD_KEY:=$HOME/.ssh/godaddy_highlow}"

# Upload under temporary names, then swap them in, so visitors never get a half-uploaded page.
# ("-" lets a command fail without stopping the batch: the old file may not exist on the first run.)
sftp -b - -i "$GD_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$GD_USER@$GD_HOST" <<EOF
cd $GD_DIR
put site/index.html index.html.tmp
put site/favicon.png favicon.png.tmp
put godaddy/.htaccess .htaccess
-rm index.html
rename index.html.tmp index.html
-rm favicon.png
rename favicon.png.tmp favicon.png
EOF
