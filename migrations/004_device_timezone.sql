CREATE TABLE IF NOT EXISTS device_settings (
    device_id text PRIMARY KEY,
    timezone text,
    location jsonb,
    config jsonb,
    last_seen_ts timestamptz
);

CREATE INDEX IF NOT EXISTS device_settings_timezone_idx ON device_settings (timezone);

CREATE OR REPLACE VIEW energy_intervals_local AS
SELECT
    e.*,
    COALESCE(ds.timezone, 'UTC') AS timezone,
    (e.start_ts AT TIME ZONE COALESCE(ds.timezone, 'UTC')) AS local_start_ts,
    (e.end_ts AT TIME ZONE COALESCE(ds.timezone, 'UTC')) AS local_end_ts,
    (e.start_ts AT TIME ZONE COALESCE(ds.timezone, 'UTC'))::date AS local_day,
    (e.start_ts AT TIME ZONE COALESCE(ds.timezone, 'UTC'))::time AS local_time,
    EXTRACT(ISODOW FROM (e.start_ts AT TIME ZONE COALESCE(ds.timezone, 'UTC')))::int AS local_isodow
FROM energy_intervals e
LEFT JOIN device_settings ds ON ds.device_id = e.device_id;

CREATE OR REPLACE VIEW energy_daily_local AS
SELECT
    e.device_id,
    e.channel,
    COALESCE(ds.timezone, 'UTC') AS timezone,
    (e.start_ts AT TIME ZONE COALESCE(ds.timezone, 'UTC'))::date AS local_day,
    SUM(e.energy_wh) AS energy_wh
FROM energy_intervals e
LEFT JOIN device_settings ds ON ds.device_id = e.device_id
GROUP BY 1, 2, 3, 4;
