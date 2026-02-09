ALTER TABLE tariffs
    ADD COLUMN IF NOT EXISTS timezone text,
    ADD COLUMN IF NOT EXISTS provider text,
    ADD COLUMN IF NOT EXISTS region text,
    ADD COLUMN IF NOT EXISTS description text,
    ADD COLUMN IF NOT EXISTS metadata jsonb;

CREATE TABLE IF NOT EXISTS tariff_components (
    id BIGSERIAL PRIMARY KEY,
    tariff_id BIGINT NOT NULL REFERENCES tariffs(id) ON DELETE CASCADE,
    name text,
    kind text NOT NULL,
    direction text NOT NULL DEFAULT 'import',
    unit text NOT NULL,
    billing_period text NOT NULL DEFAULT 'billing_cycle',
    priority int NOT NULL DEFAULT 100,
    metadata jsonb,
    CONSTRAINT tariff_components_kind_check
        CHECK (kind IN ('energy', 'distribution', 'demand', 'fixed', 'tax', 'credit', 'export')),
    CONSTRAINT tariff_components_direction_check
        CHECK (direction IN ('import', 'export', 'both')),
    CONSTRAINT tariff_components_unit_check
        CHECK (unit IN ('kwh', 'kw', 'day', 'month', 'percent', 'flat')),
    CONSTRAINT tariff_components_billing_period_check
        CHECK (billing_period IN ('billing_cycle', 'month', 'day', 'instant'))
);

CREATE INDEX IF NOT EXISTS tariff_components_tariff_id_idx ON tariff_components (tariff_id);

CREATE TABLE IF NOT EXISTS tariff_day_types (
    id BIGSERIAL PRIMARY KEY,
    tariff_id BIGINT NOT NULL REFERENCES tariffs(id) ON DELETE CASCADE,
    name text NOT NULL,
    dow_mask smallint NOT NULL,
    include_holidays boolean NOT NULL DEFAULT false,
    description text,
    CONSTRAINT tariff_day_types_unique UNIQUE (tariff_id, name),
    CONSTRAINT tariff_day_types_mask_check CHECK (dow_mask BETWEEN 0 AND 127)
);

CREATE INDEX IF NOT EXISTS tariff_day_types_tariff_id_idx ON tariff_day_types (tariff_id);

CREATE TABLE IF NOT EXISTS tariff_seasons (
    id BIGSERIAL PRIMARY KEY,
    tariff_id BIGINT NOT NULL REFERENCES tariffs(id) ON DELETE CASCADE,
    name text NOT NULL,
    start_md char(5) NOT NULL,
    end_md char(5) NOT NULL,
    year int,
    description text,
    CONSTRAINT tariff_seasons_unique UNIQUE (tariff_id, name),
    CONSTRAINT tariff_seasons_start_md_check CHECK (start_md ~ '^[0-1][0-9]-[0-3][0-9]$'),
    CONSTRAINT tariff_seasons_end_md_check CHECK (end_md ~ '^[0-1][0-9]-[0-3][0-9]$')
);

CREATE INDEX IF NOT EXISTS tariff_seasons_tariff_id_idx ON tariff_seasons (tariff_id);

CREATE TABLE IF NOT EXISTS tariff_rules (
    id BIGSERIAL PRIMARY KEY,
    component_id BIGINT NOT NULL REFERENCES tariff_components(id) ON DELETE CASCADE,
    day_type_id BIGINT REFERENCES tariff_day_types(id) ON DELETE SET NULL,
    season_id BIGINT REFERENCES tariff_seasons(id) ON DELETE SET NULL,
    effective_from date,
    effective_to date,
    rate numeric NOT NULL,
    min_kwh numeric,
    max_kwh numeric,
    min_kw numeric,
    max_kw numeric,
    priority int NOT NULL DEFAULT 100,
    metadata jsonb
);

CREATE INDEX IF NOT EXISTS tariff_rules_component_id_idx ON tariff_rules (component_id);
CREATE INDEX IF NOT EXISTS tariff_rules_day_type_id_idx ON tariff_rules (day_type_id);
CREATE INDEX IF NOT EXISTS tariff_rules_season_id_idx ON tariff_rules (season_id);
CREATE INDEX IF NOT EXISTS tariff_rules_priority_idx ON tariff_rules (component_id, priority);

CREATE TABLE IF NOT EXISTS tariff_rule_windows (
    id BIGSERIAL PRIMARY KEY,
    rule_id BIGINT NOT NULL REFERENCES tariff_rules(id) ON DELETE CASCADE,
    start_time time NOT NULL,
    end_time time NOT NULL,
    label text
);

CREATE INDEX IF NOT EXISTS tariff_rule_windows_rule_id_idx ON tariff_rule_windows (rule_id);

CREATE TABLE IF NOT EXISTS tariff_holidays (
    id BIGSERIAL PRIMARY KEY,
    tariff_id BIGINT NOT NULL REFERENCES tariffs(id) ON DELETE CASCADE,
    holiday_date date NOT NULL,
    name text,
    CONSTRAINT tariff_holidays_unique UNIQUE (tariff_id, holiday_date)
);

CREATE INDEX IF NOT EXISTS tariff_holidays_tariff_id_idx ON tariff_holidays (tariff_id);
