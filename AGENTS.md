# Shelly 3EM-63T Gen3 → Collector App (RPC → PostgreSQL) + HomeKit Notifications

## Goal
Build a small “collector” service that:
1) Reads power/energy data from a local **Shelly 3EM-63T Gen3** via **RPC** (`/rpc/...`).
2) Stores readings and interval energy data in **PostgreSQL** for analytics (trends, costs, tariffs).
3) Triggers **HomeKit notifications** by toggling a **virtual HomeKit sensor** exposed via Homebridge (e.g., motion/contact/leak) when “high usage” rules are met.

We do NOT care about Eve/Fakegato history. HomeKit is used primarily for notifications.

## Why RPC + Postgres
- Shelly Gen3 supports local RPC and provides an **EMData** component with stored interval data (`EMData.GetStatus`, `EMData.GetRecords`, `EMData.GetData`).  
  Docs: EMData component methods exist and are designed for retrieving stored energy meter data. (Shelly technical docs)
- Postgres is the “source of truth” for long-term retention, queries, costs, dashboards.

## Data Sources (Shelly RPC)
Prefer using:
- `Shelly.GetStatus` (global snapshot of all components)
- `EMData.GetStatus` / `EMData.GetData` (interval-based data from internal storage)

EMData methods to know:
- `EMData.GetStatus` – component status
- `EMData.GetRecords` – available time intervals
- `EMData.GetData` – actual recorded values
- `EMData.DeleteAllData` – ignore unless we explicitly want it

Notes:
- Use local IP of Shelly and call RPC endpoints over LAN.
- Keep polling modest; interval data is typically 5-min granularity (device-internal). For “live power”, poll status more frequently.

## High-level Architecture
### Components
1) **Collector Service**
   - Polls Shelly RPC on schedule.
   - Normalizes payloads into DB rows.
   - Evaluates alert rules (thresholds, sustained usage, time windows, cooldown).
   - Emits “event triggers” to Homebridge / HomeKit.

2) **PostgreSQL**
   - Stores:
     - Raw-ish live snapshots (power/voltage/current)
     - Interval energy records from EMData (kWh per period)
     - Tariffs and computed costs (optional materialized or computed at query time)
     - Alert events + state

3) **HomeKit Notifications**
   - Achieved by toggling a virtual accessory in Homebridge:
     - Recommended: **Motion Sensor** (reliable notifications)
     - Alternative: Contact Sensor
   - Collector toggles this accessory when alert condition is met.

### Homebridge Integration Options (choose one)
A) **Homebridge Config UI X API**
- Config UI X has a REST API accessible at `/swagger` on your Homebridge UI instance.
- Accessory control may require Homebridge “insecure mode” depending on how you plan to control accessories.
- Good if you want an HTTP call path from collector → Homebridge.

B) **MQTT path**
- Run Mosquitto.
- Use a Homebridge plugin that exposes a virtual sensor controlled via MQTT.
- Collector publishes ON/OFF.

C) **HTTP accessory plugins**
- Use a “HTTP advanced accessory” / “HTTP switch” plugin that maps HomeKit sensor state to your collector’s HTTP endpoints.
- Collector can host tiny endpoints: `/alarm/on`, `/alarm/off`.

## Implementation Plan (MVP)
### Phase 1 — Local RPC polling + DB write
- Implement RPC client:
  - Base URL: `http://SHELLY_IP/rpc/<Method>`
  - Example: `GET http://SHELLY_IP/rpc/Shelly.GetStatus`
- Store:
  - Timestamped total power (and per-phase if available)
  - Voltage/current per phase if present
- Poll interval: 10s (configurable)

### Phase 2 — Interval data ingestion for accurate kWh + costs
- Every 5 min:
  - Pull EMData interval records and/or backfill using `EMData.GetData`
  - Insert with idempotency (unique constraint on interval start/end + channel)
- Nightly backfill job:
  - Re-request previous day intervals to fill gaps if collector was down.

### Phase 3 — Alert rules + HomeKit trigger
- Rules:
  - `instant_power_w > threshold` for `duration_s`
  - Optional: separate thresholds by time-of-day
  - Add hysteresis & cooldown to prevent notification spam
- Trigger:
  - Set virtual HomeKit sensor state ON for 10–20s, then OFF
  - Log alert event to DB

## Configuration (env)
- `SHELLY_HOST` (IP or hostname)
- `SHELLY_TIMEOUT_MS`
- `POLL_LIVE_SECONDS` (e.g., 10)
- `POLL_INTERVAL_DATA_SECONDS` (e.g., 300)
- `DATABASE_URL` (Postgres)
- Alert:
  - `ALERT_POWER_W` (e.g., 4500)
  - `ALERT_SUSTAIN_SECONDS` (e.g., 120)
  - `ALERT_COOLDOWN_SECONDS` (e.g., 900)
- HomeKit trigger integration:
  - One of:
    - `HOMEBRIDGE_API_URL`, `HOMEBRIDGE_API_TOKEN`, `HOMEBRIDGE_ACCESSORY_ID`
    - OR `MQTT_URL`, `MQTT_TOPIC`
    - OR `TRIGGER_HTTP_URL` (collector calls a plugin endpoint)

## Database Schema (suggested)
### 1) Live snapshots (high frequency)
`power_readings`
- `id` bigserial pk
- `ts` timestamptz not null (indexed)
- `device_id` text
- `total_power_w` numeric
- `phase_a_power_w` numeric null
- `phase_b_power_w` numeric null
- `phase_c_power_w` numeric null
- `phase_a_voltage_v` numeric null
- `phase_b_voltage_v` numeric null
- `phase_c_voltage_v` numeric null
- `phase_a_current_a` numeric null
- `phase_b_current_a` numeric null
- `phase_c_current_a` numeric null
Indexes:
- `(ts)`
- `(device_id, ts)`

Retention note:
- Consider downsampling later (e.g., keep 10s for 30 days, 1-min for 1 year)

### 2) Interval energy (authoritative kWh periods)
`energy_intervals`
- `id` bigserial pk
- `device_id` text
- `channel` int (0..2 or phase mapping) OR text `phase` ('A','B','C','TOTAL')
- `start_ts` timestamptz not null
- `end_ts` timestamptz not null
- `energy_wh` numeric not null
- `avg_power_w` numeric null
- `meta` jsonb null
Constraints:
- unique `(device_id, channel, start_ts, end_ts)`

### 3) Tariffs (optional)
`tariffs`
- `id` bigserial pk
- `name` text
- `currency` text (e.g., 'PLN')
- `valid_from` date
- `valid_to` date null
- `rules` jsonb (time-of-day, weekend rules, etc.)

### 4) Alert events / state
`alert_events`
- `id` bigserial pk
- `ts` timestamptz
- `type` text (e.g., 'HIGH_POWER')
- `value` numeric
- `details` jsonb

`alert_state`
- `type` text pk
- `active` boolean
- `last_triggered_ts` timestamptz
- `cooldown_until_ts` timestamptz

## Reliability & Idempotency
- RPC calls can fail; implement retries with backoff.
- Store “last interval ingested” cursor per device/channel to avoid reprocessing.
- For intervals, rely on unique constraint for idempotent upserts.

## Local Dev / Ops
- Prefer Docker Compose:
  - `collector` service
  - `postgres` service
- Logging: structured JSON logs (ts, level, event, device_id)
- Healthcheck endpoint:
  - `GET /healthz` returns OK + last successful poll timestamps
- Metrics (optional):
  - Prometheus style counters for poll failures, insert counts

## Deliverables for MVP
- [ ] RPC client module (`shellyRpc.ts` / `shellyRpc.py`)
- [ ] DB layer + migrations
- [ ] Poll loop for `Shelly.GetStatus` → `power_readings`
- [ ] Interval ingestion job using EMData (`GetData` or `GetRecords`+`GetData`) → `energy_intervals`
- [ ] Alert engine with thresholds + cooldown
- [ ] One integration method to flip HomeKit virtual sensor (HTTP or MQTT)
- [ ] Compose file + README run instructions

## Notes / Open Decisions
- Choose HomeKit trigger mechanism:
  - HTTP via Homebridge UI/API vs MQTT vs HTTP accessory plugin.
- Decide if we want TimescaleDB extension (nice rollups) or plain Postgres with scheduled aggregate jobs.
- Decide whether to store per-phase detail always or only total to start.

## References
- Shelly EMData component: `EMData.GetStatus`, `EMData.GetRecords`, `EMData.GetData` (Shelly API docs)
- Homebridge Config UI X: REST API documented; Swagger at `/swagger` (Homebridge UI X wiki)