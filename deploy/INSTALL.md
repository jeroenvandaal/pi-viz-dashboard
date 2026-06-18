# Install / Deploy

Two machines are involved:

- **The Pi** — runs the dashboard server, the kiosk, and the feature scanner.
- **Your dev machine** (Mac/Linux) — where you run Claude Code; it rsyncs transcripts to the Pi.

Examples use a `YOUR_PI_HOST` SSH alias and `YOUR_USERNAME` — adapt to your setup.
Pointing the destination at an SSH alias (not a hardcoded IP) means a DHCP IP change is a
one-line `~/.ssh/config` edit. Example alias in `~/.ssh/config`:

```
Host YOUR_PI_HOST
    HostName 192.168.1.50        # your Pi's IP (or a DHCP reservation)
    User pi                       # your Pi user
    IdentityFile ~/.ssh/id_ed25519
```

## 1. Prerequisites on the Pi

- Raspberry Pi OS (Debian trixie tested) with labwc/Wayland and an HDMI touchscreen.
- Node + Claude Code, logged in (this gives the Pi its own quota credentials — no API key):
  ```bash
  ssh YOUR_PI_HOST 'curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt-get install -y nodejs && sudo npm install -g @anthropic-ai/claude-code'
  ssh -t YOUR_PI_HOST 'claude'   # run /login, then exit
  ```

## 2. Deploy the server (from your dev machine)

```bash
./deploy/deploy-to-pi.sh
```

This rsyncs the code, builds the server venv on the Pi, writes the secret env file, installs +
starts the `viz-dashboard` systemd **user** service, and wires the Chromium kiosk into labwc
autostart. It is idempotent. The shared write token is generated into a gitignored
`.viz-token.local` and copied to `~/.config/viz-dashboard.env` on the Pi.

Make the kiosk appear (or reboot the Pi):

```bash
ssh YOUR_PI_HOST "systemctl --user restart viz-dashboard; pkill chromium 2>/dev/null; labwc --reconfigure 2>/dev/null || sudo systemctl restart lightdm"
```

## 3. Enable the feature scanner on the Pi (no API key)

Extraction runs on the Pi via its own `claude -p`. Install the timer (every 20 min):

```bash
ssh YOUR_PI_HOST 'mkdir -p ~/.config/systemd/user
  cp ~/pi-dashboard/deploy/viz-scanner.service ~/.config/systemd/user/
  cp ~/pi-dashboard/deploy/viz-scanner.timer   ~/.config/systemd/user/
  systemctl --user daemon-reload
  systemctl --user enable --now viz-scanner.timer'
```

> First run note: the scanner advances a per-file cursor, so to avoid extracting your entire
> transcript history at once, baseline the cursor to "now" before enabling (set each session
> file's offset to its current size). New work is logged going forward.

## 4. Ship transcripts from your dev machine (the only host-side piece)

A dedicated, passphraseless SSH key keeps the launchd job headless:

```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/viz_pi_sync -C viz-pi-sync
ssh-copy-id -i ~/.ssh/viz_pi_sync.pub YOUR_PI_HOST
ssh YOUR_PI_HOST 'mkdir -p ~/claude-projects'
```

Then install the launchd job (edit the `YOUR_USERNAME` paths first):

```bash
cp deploy/com.vizdashboard.projects-sync.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.vizdashboard.projects-sync.plist
launchctl start com.vizdashboard.projects-sync
cat /tmp/viz-projects-sync.err   # empty = success
```

It rsyncs `~/.claude/projects/*.jsonl` to the Pi every 20 minutes — a dumb file copy, no
secrets, no LLM. (Linux dev box: use a systemd user timer instead of launchd.)

## Env vars

| Where | Var | Purpose |
|---|---|---|
| Pi service | `VIZ_DB` | SQLite path (set by the service unit) |
| Pi service | `VIZ_TOKEN` | shared secret (from `~/.config/viz-dashboard.env`) |
| Pi scanner | `VIZ_PI_URL` | `http://localhost:8080` |
| Pi scanner | `VIZ_PROJECTS_DIR` | where transcripts are rsynced (e.g. `~/claude-projects`) |
| Pi scanner | `VIZ_TOKEN` | same shared secret |
