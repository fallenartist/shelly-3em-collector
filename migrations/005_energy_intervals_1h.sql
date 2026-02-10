CREATE TABLE IF NOT EXISTS energy_intervals_1h (
    ts_hour timestamptz NOT NULL,
    device_id text NOT NULL,
    channel int,
    energy_wh numeric NOT NULL,
    avg_power_w numeric,
    samples int NOT NULL,
    PRIMARY KEY (device_id, channel, ts_hour)
);

CREATE INDEX IF NOT EXISTS energy_intervals_1h_ts_idx ON energy_intervals_1h (ts_hour);
