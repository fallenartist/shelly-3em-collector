CREATE TABLE IF NOT EXISTS power_readings (
    id BIGSERIAL PRIMARY KEY,
    ts timestamptz NOT NULL,
    device_id text,
    total_power_w numeric,
    phase_a_power_w numeric,
    phase_b_power_w numeric,
    phase_c_power_w numeric,
    phase_a_voltage_v numeric,
    phase_b_voltage_v numeric,
    phase_c_voltage_v numeric,
    phase_a_current_a numeric,
    phase_b_current_a numeric,
    phase_c_current_a numeric
);

CREATE INDEX IF NOT EXISTS power_readings_ts_idx ON power_readings (ts);
CREATE INDEX IF NOT EXISTS power_readings_device_ts_idx ON power_readings (device_id, ts);

CREATE TABLE IF NOT EXISTS power_readings_1m (
    ts_minute timestamptz NOT NULL,
    device_id text NOT NULL,
    avg_total_power_w numeric,
    avg_phase_a_power_w numeric,
    avg_phase_b_power_w numeric,
    avg_phase_c_power_w numeric,
    avg_phase_a_voltage_v numeric,
    avg_phase_b_voltage_v numeric,
    avg_phase_c_voltage_v numeric,
    avg_phase_a_current_a numeric,
    avg_phase_b_current_a numeric,
    avg_phase_c_current_a numeric,
    samples int NOT NULL,
    PRIMARY KEY (device_id, ts_minute)
);

CREATE INDEX IF NOT EXISTS power_readings_1m_ts_idx ON power_readings_1m (ts_minute);

CREATE TABLE IF NOT EXISTS energy_intervals (
    id BIGSERIAL PRIMARY KEY,
    device_id text,
    channel int,
    start_ts timestamptz NOT NULL,
    end_ts timestamptz NOT NULL,
    energy_wh numeric NOT NULL,
    avg_power_w numeric,
    meta jsonb,
    CONSTRAINT energy_intervals_unique UNIQUE (device_id, channel, start_ts, end_ts)
);

CREATE TABLE IF NOT EXISTS tariffs (
    id BIGSERIAL PRIMARY KEY,
    name text,
    currency text,
    valid_from date,
    valid_to date,
    rules jsonb
);

CREATE TABLE IF NOT EXISTS alert_events (
    id BIGSERIAL PRIMARY KEY,
    ts timestamptz,
    type text,
    value numeric,
    details jsonb
);

CREATE TABLE IF NOT EXISTS alert_state (
    type text PRIMARY KEY,
    active boolean,
    last_triggered_ts timestamptz,
    cooldown_until_ts timestamptz
);
