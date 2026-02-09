# Shelly 3EM Collector

A small, headless collector that reads power/energy data from a Shelly 3EM‑63T Gen3 over RPC, stores it in PostgreSQL, and triggers HomeKit notifications by toggling a Homebridge virtual sensor. Written to be installed on Raspberry Pi, next to Homebridge installation.

**What it does**
- Polls `Shelly.GetStatus` for live power/voltage/current.
- Ingests interval energy data from `EMData.GetRecords` + `EMData.GetData`.
- Stores data in Postgres for analytics and cost calculations.
- Triggers HomeKit notifications via [`homebridge-http-webhooks`](https://github.com/benzman81/homebridge-http-webhooks) plugin.

**What’s included**
- `collector/`: Python service (RPC polling, DB writes, alerts, webhook trigger)
- `migrations/`: SQL schema
- `docker-compose.yml`: run the collector with an external DB
- `deploy/`: systemd unit for autostart

**Install and Run (Pi, Docker)**
1. Clone the repo on the Pi.
2. Copy `.env.example` to `.env` and fill it in.
3. Build and start:

```bash
docker compose up -d --build
```

4. Apply schema:

```bash
psql "$DATABASE_URL" -f migrations/001_init.sql
```

Notes:
- If your `.env` values contain `&`, wrap them in quotes.
- If you need a clean rebuild: `docker compose build --no-cache` then `docker compose up -d`.

**Local Dev (Optional)**
```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m collector
```

**Configuration (Env Vars)**
- `SHELLY_HOST`: Shelly IP or hostname.
- `SHELLY_TIMEOUT_MS`: RPC timeout in ms.
- `POLL_LIVE_SECONDS`: live poll interval.
- `POLL_INTERVAL_DATA_SECONDS`: EMData poll interval.
- `EM_DATA_ID`: EMData component id (`emdata:0` → `0`).
- `EMDATA_LOOKBACK_RECORDS`: backfill interval count on startup.
- `DATABASE_URL`: Postgres connection string.
- `ALERT_POWER_W`: power threshold to trigger.
- `ALERT_SUSTAIN_SECONDS`: seconds above threshold before trigger.
- `ALERT_COOLDOWN_SECONDS`: cooldown between alerts.
- `ALERT_TRIGGER_SECONDS`: how long to keep sensor ON.
- `TRIGGER_HTTP_URL`: base URL with `{state}` or `/on`/`/off`.
- `TRIGGER_HTTP_ON_URL`: explicit ON URL.
- `TRIGGER_HTTP_OFF_URL`: explicit OFF URL.
- `TRIGGER_HTTP_METHOD`: `GET` or `POST`.
- `TEST_TRIGGER_TOKEN`: optional token for `/trigger/test`.
- `HEALTHZ_PORT`: health and test endpoints.
- `RETENTION_RUN_SECONDS`: retention cadence.
- `RETENTION_DOWNSAMPLE_AFTER_HOURS`: keep raw data for N hours.
- `RETENTION_MAX_DB_MB`: optional DB size cap for pruning.
- `RETENTION_PRUNE_BATCH`: rows per prune batch.
- `RETENTION_MAX_PRUNE_ITERATIONS`: max batches per run.

**HomeKit Notifications (homebridge-http-webhooks)**

Set a sensor accessory in Homebridge with:
- `Type`: `motion` or `contact`
- `Auto Release Time`: optional, e.g. 15s

Example URLs:

```env
TRIGGER_HTTP_ON_URL="http://<pi-ip>:51828/?accessoryId=powermeterLimit&state=true"
TRIGGER_HTTP_OFF_URL="http://<pi-ip>:51828/?accessoryId=powermeterLimit&state=false"
TRIGGER_HTTP_METHOD=GET
```

**Health and Test Endpoints**
- `GET /healthz` returns status and last poll timestamps.
- `GET /trigger/test` pulses the HomeKit sensor once.
- If `TEST_TRIGGER_TOKEN` is set, call `/trigger/test?token=...`.

**Data Model (Core Tables)**
- `power_readings`: live snapshots (high‑frequency).
- `energy_intervals`: interval energy data from EMData.
- `power_readings_1m`: downsampled 1‑minute aggregates.
- `alert_events`, `alert_state`: alert history and state.
- `device_settings`: device timezone + location from `Sys.GetConfig`.
- `tariffs` + `tariff_*`: flexible tariff schedules and pricing rules.

**Tariffs (Flexible Model)**
Additional tables support complex pricing (TOU, seasons, tiers, fixed/demand charges):
- `tariffs`: plan metadata (currency, timezone, provider, validity).
- `tariff_components`: cost components (energy, distribution, demand, fixed, tax, export).
- `tariff_rules`: priced rules with optional day type, season, effective dates, and tier bounds.
- `tariff_rule_windows`: time windows for peak/off‑peak/shoulder rules.
- `tariff_day_types`: weekday/weekend/holiday definitions via DOW bitmasks.
- `tariff_seasons`: seasonal date ranges (with optional year for one‑offs).
- `tariff_holidays`: holiday dates for day‑type overrides.

Seed data (example Tauron G11/G12/G12w/G13 from `temp/tauron_calculator.tsx`):
```bash
psql "$DATABASE_URL" -f migrations/002_tariffs_flexible.sql
psql "$DATABASE_URL" -f migrations/003_seed_tariffs_tauron_2026.sql
psql "$DATABASE_URL" -f migrations/004_device_timezone.sql
```

**Using Tariffs In Apps**
Recommended query pattern for “current tariff”:
```sql
-- Find active tariffs for a given date (pick the one you want by name/provider/region).
SELECT *
FROM tariffs
WHERE (valid_from IS NULL OR valid_from <= CURRENT_DATE)
  AND (valid_to IS NULL OR valid_to >= CURRENT_DATE)
ORDER BY id DESC;
```

Join helpers (example: list all rules/windows for a tariff):
```sql
SELECT
  t.name AS tariff,
  c.name AS component,
  c.kind,
  c.unit,
  r.rate,
  r.priority,
  dt.name AS day_type,
  s.name AS season,
  w.start_time,
  w.end_time
FROM tariffs t
JOIN tariff_components c ON c.tariff_id = t.id
JOIN tariff_rules r ON r.component_id = c.id
LEFT JOIN tariff_day_types dt ON dt.id = r.day_type_id
LEFT JOIN tariff_seasons s ON s.id = r.season_id
LEFT JOIN tariff_rule_windows w ON w.rule_id = r.id
WHERE t.name = 'Tauron G12 (2026)'
ORDER BY c.priority, r.priority, w.start_time;
```

Notes:
- Time windows are local to `tariffs.timezone`.
- Rules with no `day_type_id` apply to all days.
- Rules with no `season_id` apply to all seasons.

Use `energy_intervals_local` (view) for tariff alignment and local-day grouping:
```sql
SELECT
  device_id,
  channel,
  local_day,
  SUM(energy_wh) AS kwh
FROM energy_intervals_local
WHERE channel = 3
GROUP BY 1, 2, 3
ORDER BY local_day DESC;
```

**Retention Policy**

Two‑step policy:
1. Downsample raw `power_readings` older than `RETENTION_DOWNSAMPLE_AFTER_HOURS` into `power_readings_1m`.
2. Optional size cap: if `RETENTION_MAX_DB_MB` is set, delete oldest raw rows in batches.

Default raw retention is 7 days (`RETENTION_DOWNSAMPLE_AFTER_HOURS=168`).

**EMData Retention (Device vs Cloud)**

Shelly Gen3 keeps a rolling window of interval data locally. The exact window depends on device storage and period length.

Example from our device on **2026-02-09 UTC**:
- `EMData.GetRecords` reported a single block from **2026-02-02 06:00:00+00** to **2026-02-09 09:16:00+00** with a 60‑second period.
- Data earlier than that was not available via local RPC.

If you need older history (e.g., daily totals from the Shelly app), use the Shelly Cloud CSV export. Local RPC will only return what `EMData.GetRecords` advertises.

**Monitor DB Size**
```sql
SELECT pg_size_pretty(pg_database_size(current_database())) AS db_size;
SELECT relname, pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_catalog.pg_statio_user_tables
WHERE relname IN ('power_readings', 'power_readings_1m')
ORDER BY pg_total_relation_size(relid) DESC;
```

Or:

```bash
set -a
source .env
set +a
./scripts/db_size.sh
```

**Systemd Autostart (Docker Compose)**

`deploy/shelly-3em-collector.service` runs `docker compose up -d` on boot.

```bash
sudo cp deploy/shelly-3em-collector.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable shelly-3em-collector
sudo systemctl start shelly-3em-collector
```

## Using the Collected Data
Minimal examples to build your analytics UI.

Tables:
- `power_readings`: raw, high‑frequency snapshots
- `power_readings_1m`: 1‑minute averages (downsampled)
- `energy_intervals`: authoritative interval energy (Wh per period)
- `alert_events`: alert history

Example queries:

```sql
-- Latest live reading
SELECT ts, total_power_w, phase_a_power_w, phase_b_power_w, phase_c_power_w
FROM power_readings
ORDER BY ts DESC
LIMIT 1;

-- Daily kWh (sum of intervals)
SELECT
  date_trunc('day', start_ts) AS day,
  round(sum(energy_wh) / 1000.0, 3) AS kwh
FROM energy_intervals
WHERE channel = 3
GROUP BY 1
ORDER BY 1 DESC;

-- Power trend (downsampled)
SELECT ts_minute, avg_total_power_w
FROM power_readings_1m
ORDER BY ts_minute DESC
LIMIT 1440; -- last 24h
```
