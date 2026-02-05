# Shelly 3EM Collector

Collector service for Shelly 3EM-63T Gen3 RPC → PostgreSQL + HomeKit trigger.

## What’s Here
- `collector/` Python service (RPC polling, DB writes, alert + trigger)
- `migrations/` SQL schema
- `docker-compose.yml` for local/dev

## Quickstart (Local Dev)
1. Copy `.env.example` to `.env` and fill in `SHELLY_HOST` and `DATABASE_URL`.
2. Create DB schema:

```sql
-- run against your DB
\i migrations/001_init.sql
```

3. Run locally:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m collector
```

Health endpoint: `http://localhost:8080/healthz`

## Quickstart (Docker Compose)
With an external database (Neon/MyDevil/Synology), set `DATABASE_URL` in `.env` to that
connection string and include `sslmode=require` if your provider mandates TLS.

Run:

```bash
docker compose up --build
```

If you need a clean rebuild (no cache), run build and up separately:

```bash
docker compose build --no-cache
docker compose up -d
```

Note: systems with the Compose v2 plugin use `docker compose` (space). If you only have the
legacy v1 binary, use `docker-compose` (hyphen) instead.

Then apply schema (from your host machine):

```bash
psql "$DATABASE_URL" -f migrations/001_init.sql
```

## Homebridge Trigger (homebridge-http-webhooks)
You already have `homebridge-http-webhooks`. It expects a webhook URL that includes
`accessoryId` and a `state` value of `true` or `false` for boolean accessories.

Example (replace host, port, and accessoryId with your config):

```env
TRIGGER_HTTP_ON_URL=http://homebridge.local:51828/?accessoryId=power_alert&state=true
TRIGGER_HTTP_OFF_URL=http://homebridge.local:51828/?accessoryId=power_alert&state=false
TRIGGER_HTTP_METHOD=GET
```

The `webhook_port` and `accessoryId` come from your `homebridge-http-webhooks` config.
For a notification-friendly sensor, set the accessory `Type` to `motion` (or `contact`)
and optionally set `Auto Release Time` (e.g., 15s). The collector still sends an explicit
OFF after `ALERT_TRIGGER_SECONDS`, so auto-release is just a safety net.

### Test Trigger Endpoint
The collector exposes a small test endpoint that will pulse the webhook without waiting for
an alert condition:

```text
GET /trigger/test
```

If you set `TEST_TRIGGER_TOKEN`, you must pass `?token=...`:

```text
GET /trigger/test?token=YOUR_TOKEN
```

## Deployment On Homebridge Image (RPi)
The Homebridge image is a host OS. The collector is a **headless service**, so you don’t
“access” it via the Homebridge UI. You typically:

- SSH into the Pi and run it as a systemd service, or
- Install Docker on the Pi and run `docker compose` there

Either way, you’ll access the collector over the network via:

- `http://<pi-ip>:8080/healthz` for health
- Logs via `journalctl` (systemd) or `docker compose logs`

If you want, I can add a systemd unit file and install script for the Pi.

## Docker Install Guide (Homebridge Image)
Your Homebridge image is Raspberry Pi OS 32-bit (armhf). Docker Engine still supports this
platform, but Docker v28 is the last major release that will ship new 32-bit RPi OS packages.
Plan to migrate to 64-bit if you want long-term upgrades.

Use the official Docker Engine install steps for Raspberry Pi OS 32-bit. The summary below
follows the "apt repository" method:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/raspbian/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/raspbian \
  $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Post-install (optional):

```bash
sudo usermod -aG docker $USER
```

Log out and back in for group membership to apply. If you prefer the convenience script or
manual `.deb` installs, see the official Docker docs for Raspberry Pi OS 32-bit.

## EMData Notes
- `EM_DATA_ID` should match the EMData component id (`emdata:0` → `EM_DATA_ID=0`).
- `EMDATA_LOOKBACK_RECORDS` controls how many recent interval records to fetch on startup.
- Channel mapping in `energy_intervals`:
  - `0` = phase A
  - `1` = phase B
  - `2` = phase C
  - `3` = total (sum of phases)

## Retention Policy
Two-step policy:
1. **Downsample** raw `power_readings` older than `RETENTION_DOWNSAMPLE_AFTER_HOURS` into
   `power_readings_1m`.
2. **Optional size cap**: if `RETENTION_MAX_DB_MB` is set, the collector will delete oldest
   raw `power_readings` in batches until the DB size is under the threshold.

Defaults:
- `RETENTION_DOWNSAMPLE_AFTER_HOURS=24`
- `RETENTION_RUN_SECONDS=3600`
- `RETENTION_PRUNE_BATCH=20000`
- `RETENTION_MAX_PRUNE_ITERATIONS=20`

Set `RETENTION_MAX_DB_MB` if you want size-based pruning.

## Systemd (Docker Autostart)
With `restart: unless-stopped` in Compose, containers will restart when the Docker daemon
starts. To ensure `docker compose up -d` runs on boot (first start), you can install this
unit file:

`deploy/shelly-3em-collector.service`

```ini
[Unit]
Description=Shelly 3EM Collector (Docker Compose)
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/pi/shelly-3em-collector
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down

[Install]
WantedBy=multi-user.target
```

Install:

```bash
sudo cp deploy/shelly-3em-collector.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable shelly-3em-collector
sudo systemctl start shelly-3em-collector
```
