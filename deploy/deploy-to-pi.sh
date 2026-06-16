#!/usr/bin/env bash
# Deploy the viz dashboard to monitoring-pi. Run from the Mac (repo root).
# Idempotent: safe to re-run. Requires SSH alias `monitoring-pi` and the Mac to be
# logged into Claude (Keychain item "Claude Code-credentials") for the creds bootstrap.
set -euo pipefail

PI="${PI_HOST:-monitoring-pi}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOKEN_FILE="$REPO_ROOT/.viz-token.local"
cd "$REPO_ROOT"

[ -f "$TOKEN_FILE" ] || { echo "Missing $TOKEN_FILE (shared token)"; exit 1; }
TOKEN="$(cat "$TOKEN_FILE")"

echo "==> 1/6 Sync code to $PI:~/pi-dashboard"
rsync -az --delete \
  --exclude '.git' --exclude '*/.venv' --exclude '.venv' \
  --exclude '.superpowers' --exclude '*.local' --exclude '*.db' \
  --exclude '__pycache__' --exclude '*.pyc' \
  ./ "$PI:pi-dashboard/"

echo "==> 2/6 Create/refresh server venv on the Pi"
ssh "$PI" 'cd ~/pi-dashboard && (test -d server/.venv || python3 -m venv server/.venv) && server/.venv/bin/pip -q install -r server/requirements.txt'

echo "==> 3/6 Write secret env file (~/.config/viz-dashboard.env, 600)"
ssh "$PI" "umask 077; mkdir -p ~/.config; printf 'VIZ_TOKEN=%s\n' '$TOKEN' > ~/.config/viz-dashboard.env"

echo "==> 4/6 Bootstrap Claude credentials from this Mac's Keychain (temporary; replace with 'claude login' on the Pi when convenient)"
CREDS_JSON="$(security find-generic-password -s 'Claude Code-credentials' -w 2>/dev/null || true)"
if [ -n "$CREDS_JSON" ]; then
  ssh "$PI" "umask 077; mkdir -p ~/.claude; cat > ~/.claude/.credentials.json" <<< "$CREDS_JSON"
  echo "    creds written to $PI:~/.claude/.credentials.json"
else
  echo "    WARN: no Keychain creds found on this Mac; quota will be stale until 'claude login' on the Pi."
fi

echo "==> 5/6 Install + start systemd user service"
ssh "$PI" 'mkdir -p ~/.config/systemd/user && cp ~/pi-dashboard/deploy/viz-dashboard.service ~/.config/systemd/user/ && systemctl --user daemon-reload && systemctl --user enable --now viz-dashboard && (loginctl enable-linger "$USER" 2>/dev/null || true)'
sleep 2
ssh "$PI" 'systemctl --user is-active viz-dashboard && curl -s localhost:8080/api/quota | head -c 400; echo'

echo "==> 6/6 Wire Chromium kiosk into labwc autostart (idempotent)"
ssh "$PI" '
  AUTO=~/.config/labwc/autostart; mkdir -p ~/.config/labwc; touch "$AUTO"
  if ! grep -q "Viz Dashboard kiosk" "$AUTO"; then
    cat ~/pi-dashboard/deploy/labwc-autostart.snippet >> "$AUTO"
    echo "    kiosk snippet appended"
  else
    echo "    kiosk snippet already present"
  fi
'
echo
echo "Done. Reboot the Pi or run:  ssh $PI \"systemctl --user restart viz-dashboard; pkill chromium; labwc --reconfigure 2>/dev/null || sudo systemctl restart lightdm\""
echo "The dashboard should appear fullscreen on the Pi's screen."
