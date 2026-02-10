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

**Configuration**
The collector reads env vars from `.env` (see `.env.example`). Defaults below are from code; any value
set in `.env` overrides the default. `.env.example` may suggest more production‑friendly values.

**Shelly & RPC**
- `SHELLY_HOST` (required): Shelly IP/hostname.
- `SHELLY_TIMEOUT_MS` (default `5000`): RPC timeout in ms. Lower = faster failure on network issues.

**Polling**
- `POLL_LIVE_SECONDS` (default `10`): live snapshot cadence. Lower = higher resolution + more DB growth.
- `POLL_INTERVAL_DATA_SECONDS` (default `300`): EMData poll cadence. Lower = fresher interval data;
  higher = more lag, same total interval volume.
- `EM_DATA_ID` (default `0`): EMData component id (`emdata:0` → `0`).
- `EMDATA_LOOKBACK_RECORDS` (default `720`): how many interval records to backfill on startup.
  Higher = slower startup, more gap‑filling.

**Database**
- `DATABASE_URL` (required): Postgres connection string.

**Alerts**
- `ALERT_POWER_W` (default `4500`): power threshold to trigger.
- `ALERT_SUSTAIN_SECONDS` (default `120`): seconds above threshold before trigger.
- `ALERT_COOLDOWN_SECONDS` (default `900`): cooldown between alerts.
- `ALERT_TRIGGER_SECONDS` (default `15`): how long to keep sensor ON.

**HomeKit Trigger**
- `TRIGGER_HTTP_URL`: base URL with `{state}` or `/on`/`/off`.
- `TRIGGER_HTTP_ON_URL`: explicit ON URL.
- `TRIGGER_HTTP_OFF_URL`: explicit OFF URL.
- `TRIGGER_HTTP_METHOD` (default `POST`): `GET` or `POST`.

**Service**
- `HEALTHZ_PORT` (default `8080`): health and test endpoints.
- `TEST_TRIGGER_TOKEN`: optional token for `/trigger/test`.

**Retention & Storage**
- `RETENTION_RUN_SECONDS` (default `3600`): retention loop cadence.
- `RETENTION_DOWNSAMPLE_AFTER_HOURS` (default `24`): keep raw data for N hours before downsampling.
  Set to `0`/empty to disable downsampling.
- `RETENTION_LOW_RES_MINUTES` (default `1`): bucket size for low‑res rows. Higher = smaller DB,
  less detail.
- `RETENTION_LOW_RES_MAX_DAYS` (default `null`): optional retention window for low‑res rows.
- `RETENTION_INTERVAL_DOWNSAMPLE_AFTER_DAYS` (default `1`): keep 1‑minute interval rows for N days,
  then downsample into hourly buckets.
- `RETENTION_INTERVAL_LOW_RES_HOURS` (default `1`): bucket size for `energy_intervals_1h`.
- `RETENTION_INTERVAL_LOW_RES_MAX_DAYS` (default `null`): optional retention window for hourly rows.
- `RETENTION_MAX_DB_MB` (default `null`): optional size cap. When exceeded, oldest rows are deleted
  across raw + low‑res. If `RETENTION_PRUNE_INCLUDE_INTERVALS=true`, interval rows can be pruned too.
- `RETENTION_PRUNE_INCLUDE_INTERVALS` (default `false`): include `energy_intervals` in size‑cap pruning.

Prune behavior details (when `RETENTION_MAX_DB_MB` is set):
- The collector computes a **time cutoff** and deletes all rows **older than that cutoff**
  across `power_readings` and `power_readings_1m` (and interval tables if enabled).
- The cutoff is estimated from the current storage size and the age span of the included tables,
  so dense data doesn’t get unfairly over‑pruned.

**Recommended Profiles**
Goal: understand **behavior patterns** (typical day/workweek/weekend) and keep **long‑term kWh**.

Balanced default (good signal, reasonable DB growth):
- `POLL_LIVE_SECONDS=10`
- `POLL_INTERVAL_DATA_SECONDS=300` (device period is usually 60s)
- `RETENTION_DOWNSAMPLE_AFTER_HOURS=720` (keep ~30 days of high‑res)
- `RETENTION_LOW_RES_MINUTES=5` (good for behavior patterns)
- `RETENTION_LOW_RES_MAX_DAYS=365` (1 year of low‑res shape)
- `RETENTION_INTERVAL_DOWNSAMPLE_AFTER_DAYS=1` (keep 1‑minute intervals for 1 day)
- `RETENTION_INTERVAL_LOW_RES_HOURS=1` (hourly kWh long‑term)

If you want more detail in behavior patterns:
- Lower `RETENTION_LOW_RES_MINUTES` to `1` (more storage).

If you only care about long‑term kWh:
- Increase `RETENTION_LOW_RES_MINUTES` (e.g. 15) or set `RETENTION_LOW_RES_MAX_DAYS`.

**One‑Off Prune Script**
Use this to apply the current `.env` retention settings immediately:
```bash
python3 scripts/prune_db.py --yes
```
This is irreversible. If you changed settings to **higher resolution** than before, the script
cannot recreate missing data.

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
- `energy_intervals_1h`: downsampled hourly kWh (from `energy_intervals`).
- `power_readings_1m`: downsampled aggregates (bucket size via `RETENTION_LOW_RES_MINUTES`).
- `alert_events`, `alert_state`: alert history and state.
- `device_settings`: device timezone + location from `Sys.GetConfig`.
- `tariffs` + `tariff_*`: flexible tariff schedules and pricing rules.

Why keep both `energy_intervals` and downsampled `power_readings_1m`?
- `energy_intervals` are **authoritative kWh** from the meter’s internal storage. Best for tariffs,
  daily/monthly totals, and long‑term consumption accuracy.
- `power_readings_1m` are **averaged power snapshots**. Best for **behavior patterns** (load shape,
  peaks, weekday/weekend differences) that energy totals alone can’t show.
For long‑term storage, `energy_intervals` are downsampled into `energy_intervals_1h` based on
`RETENTION_INTERVAL_DOWNSAMPLE_AFTER_DAYS` and `RETENTION_INTERVAL_LOW_RES_HOURS`.

**Schema Add‑Ons**
Apply these after `migrations/001_init.sql` as needed:
```bash
# Tariff schema + example Tauron seed data
psql "$DATABASE_URL" -f migrations/002_tariffs_flexible.sql
psql "$DATABASE_URL" -f migrations/003_seed_tariffs_tauron_2026.sql

# Device timezone + local‑time views
psql "$DATABASE_URL" -f migrations/004_device_timezone.sql

# Hourly interval table (downsampled kWh)
psql "$DATABASE_URL" -f migrations/005_energy_intervals_1h.sql
```

**Device Timezone & Local Day**
On startup the collector calls `Sys.GetConfig`, reads `location.tz`, and upserts into `device_settings`.
Restart the collector after applying `migrations/004_device_timezone.sql` so the table is populated.

Inspect the device settings:
```sql
SELECT device_id, timezone, location, last_seen_ts
FROM device_settings
ORDER BY last_seen_ts DESC;
```

Use local‑time views for daily grouping and tariff alignment:
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

**Tariffs (Flexible Model)**
Additional tables support complex pricing (TOU, seasons, tiers, fixed/demand charges):
- `tariffs`: plan metadata (currency, timezone, provider, validity).
- `tariff_components`: cost components (energy, distribution, demand, fixed, tax, export).
- `tariff_rules`: priced rules with optional day type, season, effective dates, and tier bounds.
- `tariff_rule_windows`: time windows for peak/off‑peak/shoulder rules.
- `tariff_day_types`: weekday/weekend/holiday definitions via DOW bitmasks.
- `tariff_seasons`: seasonal date ranges (with optional year for one‑offs).
- `tariff_holidays`: holiday dates for day‑type overrides.

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
