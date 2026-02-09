-- Seed example tariffs based on temp/tauron_calculator.tsx (prices include energy + distribution).
-- DOW mask bits: Mon=1, Tue=2, Wed=4, Thu=8, Fri=16, Sat=32, Sun=64.

-- -----------------------
-- Tauron G11 (single zone)
-- -----------------------
INSERT INTO tariffs (
    name, description, currency, timezone, provider, region, valid_from, valid_to, metadata
)
SELECT
    'Tauron G11 (2026)',
    'Example G11 tariff (single zone). Prices from temp/tauron_calculator.tsx; energy + distribution included.',
    'PLN',
    'Europe/Warsaw',
    'Tauron',
    'PL',
    '2026-01-01',
    NULL,
    jsonb_build_object('source', 'temp/tauron_calculator.tsx')
WHERE NOT EXISTS (
    SELECT 1 FROM tariffs WHERE name = 'Tauron G11 (2026)'
);

INSERT INTO tariff_components (tariff_id, name, kind, direction, unit, billing_period, priority, metadata)
SELECT t.id, 'Energy total', 'energy', 'import', 'kwh', 'billing_cycle', 100,
       jsonb_build_object('includes', 'energy+distribution')
FROM (SELECT id FROM tariffs WHERE name = 'Tauron G11 (2026)' ORDER BY id LIMIT 1) t
WHERE NOT EXISTS (
    SELECT 1 FROM tariff_components c WHERE c.tariff_id = t.id AND c.name = 'Energy total'
);

INSERT INTO tariff_components (tariff_id, name, kind, direction, unit, billing_period, priority, metadata)
SELECT t.id, 'Trade fee', 'fixed', 'import', 'month', 'month', 200,
       jsonb_build_object('source', 'temp/tauron_calculator.tsx')
FROM (SELECT id FROM tariffs WHERE name = 'Tauron G11 (2026)' ORDER BY id LIMIT 1) t
WHERE NOT EXISTS (
    SELECT 1 FROM tariff_components c WHERE c.tariff_id = t.id AND c.name = 'Trade fee'
);

INSERT INTO tariff_rules (component_id, rate, priority, metadata)
SELECT c.id, 1.05, 100, jsonb_build_object('price_key', 'g11')
FROM tariff_components c
JOIN tariffs t ON t.id = c.tariff_id
WHERE t.name = 'Tauron G11 (2026)' AND c.name = 'Energy total'
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rules r WHERE r.component_id = c.id AND r.rate = 1.05
  );

INSERT INTO tariff_rule_windows (rule_id, start_time, end_time, label)
SELECT r.id, '00:00', '23:59:59', 'all-day'
FROM tariff_rules r
JOIN tariff_components c ON c.id = r.component_id
JOIN tariffs t ON t.id = c.tariff_id
WHERE t.name = 'Tauron G11 (2026)' AND c.name = 'Energy total' AND r.rate = 1.05
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rule_windows w WHERE w.rule_id = r.id
  );

INSERT INTO tariff_rules (component_id, rate, priority, metadata)
SELECT c.id, 31.50, 100, jsonb_build_object('price_key', 'tradeFee')
FROM tariff_components c
JOIN tariffs t ON t.id = c.tariff_id
WHERE t.name = 'Tauron G11 (2026)' AND c.name = 'Trade fee'
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rules r WHERE r.component_id = c.id AND r.rate = 31.50
  );

-- -----------------------
-- Tauron G12 (two zones)
-- -----------------------
INSERT INTO tariffs (
    name, description, currency, timezone, provider, region, valid_from, valid_to, metadata
)
SELECT
    'Tauron G12 (2026)',
    'Example G12 tariff. Peak: 06:00-13:00, 15:00-22:00; off-peak otherwise. Prices from temp/tauron_calculator.tsx.',
    'PLN',
    'Europe/Warsaw',
    'Tauron',
    'PL',
    '2026-01-01',
    NULL,
    jsonb_build_object('source', 'temp/tauron_calculator.tsx')
WHERE NOT EXISTS (
    SELECT 1 FROM tariffs WHERE name = 'Tauron G12 (2026)'
);

INSERT INTO tariff_components (tariff_id, name, kind, direction, unit, billing_period, priority, metadata)
SELECT t.id, 'Energy total', 'energy', 'import', 'kwh', 'billing_cycle', 100,
       jsonb_build_object('includes', 'energy+distribution')
FROM (SELECT id FROM tariffs WHERE name = 'Tauron G12 (2026)' ORDER BY id LIMIT 1) t
WHERE NOT EXISTS (
    SELECT 1 FROM tariff_components c WHERE c.tariff_id = t.id AND c.name = 'Energy total'
);

INSERT INTO tariff_components (tariff_id, name, kind, direction, unit, billing_period, priority, metadata)
SELECT t.id, 'Trade fee', 'fixed', 'import', 'month', 'month', 200,
       jsonb_build_object('source', 'temp/tauron_calculator.tsx')
FROM (SELECT id FROM tariffs WHERE name = 'Tauron G12 (2026)' ORDER BY id LIMIT 1) t
WHERE NOT EXISTS (
    SELECT 1 FROM tariff_components c WHERE c.tariff_id = t.id AND c.name = 'Trade fee'
);

-- Peak rule
INSERT INTO tariff_rules (component_id, rate, priority, metadata)
SELECT c.id, 1.21, 100, jsonb_build_object('price_key', 'g12.peak')
FROM tariff_components c
JOIN tariffs t ON t.id = c.tariff_id
WHERE t.name = 'Tauron G12 (2026)' AND c.name = 'Energy total'
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rules r WHERE r.component_id = c.id AND r.rate = 1.21
  );

INSERT INTO tariff_rule_windows (rule_id, start_time, end_time, label)
SELECT r.id, '06:00', '13:00', 'peak-morning'
FROM tariff_rules r
JOIN tariff_components c ON c.id = r.component_id
JOIN tariffs t ON t.id = c.tariff_id
WHERE t.name = 'Tauron G12 (2026)' AND c.name = 'Energy total' AND r.rate = 1.21
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rule_windows w WHERE w.rule_id = r.id AND w.label = 'peak-morning'
  );

INSERT INTO tariff_rule_windows (rule_id, start_time, end_time, label)
SELECT r.id, '15:00', '22:00', 'peak-evening'
FROM tariff_rules r
JOIN tariff_components c ON c.id = r.component_id
JOIN tariffs t ON t.id = c.tariff_id
WHERE t.name = 'Tauron G12 (2026)' AND c.name = 'Energy total' AND r.rate = 1.21
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rule_windows w WHERE w.rule_id = r.id AND w.label = 'peak-evening'
  );

-- Off-peak rule
INSERT INTO tariff_rules (component_id, rate, priority, metadata)
SELECT c.id, 0.72, 110, jsonb_build_object('price_key', 'g12.offPeak')
FROM tariff_components c
JOIN tariffs t ON t.id = c.tariff_id
WHERE t.name = 'Tauron G12 (2026)' AND c.name = 'Energy total'
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rules r WHERE r.component_id = c.id AND r.rate = 0.72
  );

INSERT INTO tariff_rule_windows (rule_id, start_time, end_time, label)
SELECT r.id, '00:00', '06:00', 'off-peak-night'
FROM tariff_rules r
JOIN tariff_components c ON c.id = r.component_id
JOIN tariffs t ON t.id = c.tariff_id
WHERE t.name = 'Tauron G12 (2026)' AND c.name = 'Energy total' AND r.rate = 0.72
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rule_windows w WHERE w.rule_id = r.id AND w.label = 'off-peak-night'
  );

INSERT INTO tariff_rule_windows (rule_id, start_time, end_time, label)
SELECT r.id, '13:00', '15:00', 'off-peak-noon'
FROM tariff_rules r
JOIN tariff_components c ON c.id = r.component_id
JOIN tariffs t ON t.id = c.tariff_id
WHERE t.name = 'Tauron G12 (2026)' AND c.name = 'Energy total' AND r.rate = 0.72
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rule_windows w WHERE w.rule_id = r.id AND w.label = 'off-peak-noon'
  );

INSERT INTO tariff_rule_windows (rule_id, start_time, end_time, label)
SELECT r.id, '22:00', '23:59:59', 'off-peak-late'
FROM tariff_rules r
JOIN tariff_components c ON c.id = r.component_id
JOIN tariffs t ON t.id = c.tariff_id
WHERE t.name = 'Tauron G12 (2026)' AND c.name = 'Energy total' AND r.rate = 0.72
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rule_windows w WHERE w.rule_id = r.id AND w.label = 'off-peak-late'
  );

INSERT INTO tariff_rules (component_id, rate, priority, metadata)
SELECT c.id, 31.50, 100, jsonb_build_object('price_key', 'tradeFee')
FROM tariff_components c
JOIN tariffs t ON t.id = c.tariff_id
WHERE t.name = 'Tauron G12 (2026)' AND c.name = 'Trade fee'
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rules r WHERE r.component_id = c.id AND r.rate = 31.50
  );

-- -----------------------
-- Tauron G12w (weekend off-peak)
-- -----------------------
INSERT INTO tariffs (
    name, description, currency, timezone, provider, region, valid_from, valid_to, metadata
)
SELECT
    'Tauron G12w (2026)',
    'Example G12w tariff. Weekends: off-peak all day; weekdays like G12. Prices from temp/tauron_calculator.tsx.',
    'PLN',
    'Europe/Warsaw',
    'Tauron',
    'PL',
    '2026-01-01',
    NULL,
    jsonb_build_object('source', 'temp/tauron_calculator.tsx')
WHERE NOT EXISTS (
    SELECT 1 FROM tariffs WHERE name = 'Tauron G12w (2026)'
);

INSERT INTO tariff_day_types (tariff_id, name, dow_mask, include_holidays, description)
SELECT t.id, 'weekday', 31, false, 'Mon-Fri'
FROM (SELECT id FROM tariffs WHERE name = 'Tauron G12w (2026)' ORDER BY id LIMIT 1) t
WHERE NOT EXISTS (
    SELECT 1 FROM tariff_day_types d WHERE d.tariff_id = t.id AND d.name = 'weekday'
);

INSERT INTO tariff_day_types (tariff_id, name, dow_mask, include_holidays, description)
SELECT t.id, 'weekend', 96, false, 'Sat-Sun'
FROM (SELECT id FROM tariffs WHERE name = 'Tauron G12w (2026)' ORDER BY id LIMIT 1) t
WHERE NOT EXISTS (
    SELECT 1 FROM tariff_day_types d WHERE d.tariff_id = t.id AND d.name = 'weekend'
);

INSERT INTO tariff_components (tariff_id, name, kind, direction, unit, billing_period, priority, metadata)
SELECT t.id, 'Energy total', 'energy', 'import', 'kwh', 'billing_cycle', 100,
       jsonb_build_object('includes', 'energy+distribution')
FROM (SELECT id FROM tariffs WHERE name = 'Tauron G12w (2026)' ORDER BY id LIMIT 1) t
WHERE NOT EXISTS (
    SELECT 1 FROM tariff_components c WHERE c.tariff_id = t.id AND c.name = 'Energy total'
);

INSERT INTO tariff_components (tariff_id, name, kind, direction, unit, billing_period, priority, metadata)
SELECT t.id, 'Trade fee', 'fixed', 'import', 'month', 'month', 200,
       jsonb_build_object('source', 'temp/tauron_calculator.tsx')
FROM (SELECT id FROM tariffs WHERE name = 'Tauron G12w (2026)' ORDER BY id LIMIT 1) t
WHERE NOT EXISTS (
    SELECT 1 FROM tariff_components c WHERE c.tariff_id = t.id AND c.name = 'Trade fee'
);

-- Weekday peak rule
INSERT INTO tariff_rules (component_id, day_type_id, rate, priority, metadata)
SELECT c.id, d.id, 1.32, 100, jsonb_build_object('price_key', 'g12w.peak')
FROM tariff_components c
JOIN tariffs t ON t.id = c.tariff_id
JOIN tariff_day_types d ON d.tariff_id = t.id AND d.name = 'weekday'
WHERE t.name = 'Tauron G12w (2026)' AND c.name = 'Energy total'
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rules r WHERE r.component_id = c.id AND r.day_type_id = d.id AND r.rate = 1.32
  );

INSERT INTO tariff_rule_windows (rule_id, start_time, end_time, label)
SELECT r.id, '06:00', '13:00', 'peak-morning'
FROM tariff_rules r
JOIN tariff_components c ON c.id = r.component_id
JOIN tariffs t ON t.id = c.tariff_id
JOIN tariff_day_types d ON d.id = r.day_type_id AND d.name = 'weekday'
WHERE t.name = 'Tauron G12w (2026)' AND c.name = 'Energy total' AND r.rate = 1.32
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rule_windows w WHERE w.rule_id = r.id AND w.label = 'peak-morning'
  );

INSERT INTO tariff_rule_windows (rule_id, start_time, end_time, label)
SELECT r.id, '15:00', '22:00', 'peak-evening'
FROM tariff_rules r
JOIN tariff_components c ON c.id = r.component_id
JOIN tariffs t ON t.id = c.tariff_id
JOIN tariff_day_types d ON d.id = r.day_type_id AND d.name = 'weekday'
WHERE t.name = 'Tauron G12w (2026)' AND c.name = 'Energy total' AND r.rate = 1.32
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rule_windows w WHERE w.rule_id = r.id AND w.label = 'peak-evening'
  );

-- Weekday off-peak rule
INSERT INTO tariff_rules (component_id, day_type_id, rate, priority, metadata)
SELECT c.id, d.id, 0.72, 110, jsonb_build_object('price_key', 'g12w.offPeak')
FROM tariff_components c
JOIN tariffs t ON t.id = c.tariff_id
JOIN tariff_day_types d ON d.tariff_id = t.id AND d.name = 'weekday'
WHERE t.name = 'Tauron G12w (2026)' AND c.name = 'Energy total'
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rules r WHERE r.component_id = c.id AND r.day_type_id = d.id AND r.rate = 0.72
  );

INSERT INTO tariff_rule_windows (rule_id, start_time, end_time, label)
SELECT r.id, '00:00', '06:00', 'off-peak-night'
FROM tariff_rules r
JOIN tariff_components c ON c.id = r.component_id
JOIN tariffs t ON t.id = c.tariff_id
JOIN tariff_day_types d ON d.id = r.day_type_id AND d.name = 'weekday'
WHERE t.name = 'Tauron G12w (2026)' AND c.name = 'Energy total' AND r.rate = 0.72
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rule_windows w WHERE w.rule_id = r.id AND w.label = 'off-peak-night'
  );

INSERT INTO tariff_rule_windows (rule_id, start_time, end_time, label)
SELECT r.id, '13:00', '15:00', 'off-peak-noon'
FROM tariff_rules r
JOIN tariff_components c ON c.id = r.component_id
JOIN tariffs t ON t.id = c.tariff_id
JOIN tariff_day_types d ON d.id = r.day_type_id AND d.name = 'weekday'
WHERE t.name = 'Tauron G12w (2026)' AND c.name = 'Energy total' AND r.rate = 0.72
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rule_windows w WHERE w.rule_id = r.id AND w.label = 'off-peak-noon'
  );

INSERT INTO tariff_rule_windows (rule_id, start_time, end_time, label)
SELECT r.id, '22:00', '23:59:59', 'off-peak-late'
FROM tariff_rules r
JOIN tariff_components c ON c.id = r.component_id
JOIN tariffs t ON t.id = c.tariff_id
JOIN tariff_day_types d ON d.id = r.day_type_id AND d.name = 'weekday'
WHERE t.name = 'Tauron G12w (2026)' AND c.name = 'Energy total' AND r.rate = 0.72
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rule_windows w WHERE w.rule_id = r.id AND w.label = 'off-peak-late'
  );

-- Weekend off-peak (all day)
INSERT INTO tariff_rules (component_id, day_type_id, rate, priority, metadata)
SELECT c.id, d.id, 0.72, 120, jsonb_build_object('price_key', 'g12w.offPeak.weekend')
FROM tariff_components c
JOIN tariffs t ON t.id = c.tariff_id
JOIN tariff_day_types d ON d.tariff_id = t.id AND d.name = 'weekend'
WHERE t.name = 'Tauron G12w (2026)' AND c.name = 'Energy total'
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rules r WHERE r.component_id = c.id AND r.day_type_id = d.id AND r.rate = 0.72
  );

INSERT INTO tariff_rule_windows (rule_id, start_time, end_time, label)
SELECT r.id, '00:00', '23:59:59', 'weekend-all-day'
FROM tariff_rules r
JOIN tariff_components c ON c.id = r.component_id
JOIN tariffs t ON t.id = c.tariff_id
JOIN tariff_day_types d ON d.id = r.day_type_id AND d.name = 'weekend'
WHERE t.name = 'Tauron G12w (2026)' AND c.name = 'Energy total' AND r.rate = 0.72
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rule_windows w WHERE w.rule_id = r.id AND w.label = 'weekend-all-day'
  );

INSERT INTO tariff_rules (component_id, rate, priority, metadata)
SELECT c.id, 31.50, 100, jsonb_build_object('price_key', 'tradeFee')
FROM tariff_components c
JOIN tariffs t ON t.id = c.tariff_id
WHERE t.name = 'Tauron G12w (2026)' AND c.name = 'Trade fee'
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rules r WHERE r.component_id = c.id AND r.rate = 31.50
  );

-- -----------------------
-- Tauron G13 (three zones)
-- -----------------------
INSERT INTO tariffs (
    name, description, currency, timezone, provider, region, valid_from, valid_to, metadata
)
SELECT
    'Tauron G13 (2026)',
    'Example G13 tariff. Weekends: off-peak all day. Weekdays: 07:00-13:00 peak; season-dependent afternoon peak (winter 16:00-21:00, summer 19:00-22:00). Prices from temp/tauron_calculator.tsx.',
    'PLN',
    'Europe/Warsaw',
    'Tauron',
    'PL',
    '2026-01-01',
    NULL,
    jsonb_build_object('source', 'temp/tauron_calculator.tsx')
WHERE NOT EXISTS (
    SELECT 1 FROM tariffs WHERE name = 'Tauron G13 (2026)'
);

INSERT INTO tariff_day_types (tariff_id, name, dow_mask, include_holidays, description)
SELECT t.id, 'weekday', 31, false, 'Mon-Fri'
FROM (SELECT id FROM tariffs WHERE name = 'Tauron G13 (2026)' ORDER BY id LIMIT 1) t
WHERE NOT EXISTS (
    SELECT 1 FROM tariff_day_types d WHERE d.tariff_id = t.id AND d.name = 'weekday'
);

INSERT INTO tariff_day_types (tariff_id, name, dow_mask, include_holidays, description)
SELECT t.id, 'weekend', 96, false, 'Sat-Sun'
FROM (SELECT id FROM tariffs WHERE name = 'Tauron G13 (2026)' ORDER BY id LIMIT 1) t
WHERE NOT EXISTS (
    SELECT 1 FROM tariff_day_types d WHERE d.tariff_id = t.id AND d.name = 'weekend'
);

INSERT INTO tariff_seasons (tariff_id, name, start_md, end_md, year, description)
SELECT t.id, 'summer', '04-01', '09-30', NULL, 'Assumed summer season for example data'
FROM (SELECT id FROM tariffs WHERE name = 'Tauron G13 (2026)' ORDER BY id LIMIT 1) t
WHERE NOT EXISTS (
    SELECT 1 FROM tariff_seasons s WHERE s.tariff_id = t.id AND s.name = 'summer'
);

INSERT INTO tariff_seasons (tariff_id, name, start_md, end_md, year, description)
SELECT t.id, 'winter', '10-01', '03-31', NULL, 'Assumed winter season for example data'
FROM (SELECT id FROM tariffs WHERE name = 'Tauron G13 (2026)' ORDER BY id LIMIT 1) t
WHERE NOT EXISTS (
    SELECT 1 FROM tariff_seasons s WHERE s.tariff_id = t.id AND s.name = 'winter'
);

INSERT INTO tariff_components (tariff_id, name, kind, direction, unit, billing_period, priority, metadata)
SELECT t.id, 'Energy total', 'energy', 'import', 'kwh', 'billing_cycle', 100,
       jsonb_build_object('includes', 'energy+distribution')
FROM (SELECT id FROM tariffs WHERE name = 'Tauron G13 (2026)' ORDER BY id LIMIT 1) t
WHERE NOT EXISTS (
    SELECT 1 FROM tariff_components c WHERE c.tariff_id = t.id AND c.name = 'Energy total'
);

INSERT INTO tariff_components (tariff_id, name, kind, direction, unit, billing_period, priority, metadata)
SELECT t.id, 'Trade fee', 'fixed', 'import', 'month', 'month', 200,
       jsonb_build_object('source', 'temp/tauron_calculator.tsx')
FROM (SELECT id FROM tariffs WHERE name = 'Tauron G13 (2026)' ORDER BY id LIMIT 1) t
WHERE NOT EXISTS (
    SELECT 1 FROM tariff_components c WHERE c.tariff_id = t.id AND c.name = 'Trade fee'
);

-- Weekday morning peak (07:00-13:00)
INSERT INTO tariff_rules (component_id, day_type_id, rate, priority, metadata)
SELECT c.id, d.id, 1.04, 100, jsonb_build_object('price_key', 'g13.morningPeak')
FROM tariff_components c
JOIN tariffs t ON t.id = c.tariff_id
JOIN tariff_day_types d ON d.tariff_id = t.id AND d.name = 'weekday'
WHERE t.name = 'Tauron G13 (2026)' AND c.name = 'Energy total'
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rules r WHERE r.component_id = c.id AND r.day_type_id = d.id AND r.rate = 1.04
  );

INSERT INTO tariff_rule_windows (rule_id, start_time, end_time, label)
SELECT r.id, '07:00', '13:00', 'morning-peak'
FROM tariff_rules r
JOIN tariff_components c ON c.id = r.component_id
JOIN tariffs t ON t.id = c.tariff_id
JOIN tariff_day_types d ON d.id = r.day_type_id AND d.name = 'weekday'
WHERE t.name = 'Tauron G13 (2026)' AND c.name = 'Energy total' AND r.rate = 1.04
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rule_windows w WHERE w.rule_id = r.id AND w.label = 'morning-peak'
  );

-- Weekday afternoon peak (seasonal)
INSERT INTO tariff_rules (component_id, day_type_id, season_id, rate, priority, metadata)
SELECT c.id, d.id, s.id, 1.52, 110, jsonb_build_object('price_key', 'g13.afternoonPeak', 'season', 'winter')
FROM tariff_components c
JOIN tariffs t ON t.id = c.tariff_id
JOIN tariff_day_types d ON d.tariff_id = t.id AND d.name = 'weekday'
JOIN tariff_seasons s ON s.tariff_id = t.id AND s.name = 'winter'
WHERE t.name = 'Tauron G13 (2026)' AND c.name = 'Energy total'
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rules r WHERE r.component_id = c.id AND r.day_type_id = d.id AND r.season_id = s.id AND r.rate = 1.52
  );

INSERT INTO tariff_rule_windows (rule_id, start_time, end_time, label)
SELECT r.id, '16:00', '21:00', 'afternoon-peak-winter'
FROM tariff_rules r
JOIN tariff_components c ON c.id = r.component_id
JOIN tariffs t ON t.id = c.tariff_id
JOIN tariff_seasons s ON s.id = r.season_id AND s.name = 'winter'
WHERE t.name = 'Tauron G13 (2026)' AND c.name = 'Energy total' AND r.rate = 1.52
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rule_windows w WHERE w.rule_id = r.id AND w.label = 'afternoon-peak-winter'
  );

INSERT INTO tariff_rules (component_id, day_type_id, season_id, rate, priority, metadata)
SELECT c.id, d.id, s.id, 1.52, 110, jsonb_build_object('price_key', 'g13.afternoonPeak', 'season', 'summer')
FROM tariff_components c
JOIN tariffs t ON t.id = c.tariff_id
JOIN tariff_day_types d ON d.tariff_id = t.id AND d.name = 'weekday'
JOIN tariff_seasons s ON s.tariff_id = t.id AND s.name = 'summer'
WHERE t.name = 'Tauron G13 (2026)' AND c.name = 'Energy total'
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rules r WHERE r.component_id = c.id AND r.day_type_id = d.id AND r.season_id = s.id AND r.rate = 1.52
  );

INSERT INTO tariff_rule_windows (rule_id, start_time, end_time, label)
SELECT r.id, '19:00', '22:00', 'afternoon-peak-summer'
FROM tariff_rules r
JOIN tariff_components c ON c.id = r.component_id
JOIN tariffs t ON t.id = c.tariff_id
JOIN tariff_seasons s ON s.id = r.season_id AND s.name = 'summer'
WHERE t.name = 'Tauron G13 (2026)' AND c.name = 'Energy total' AND r.rate = 1.52
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rule_windows w WHERE w.rule_id = r.id AND w.label = 'afternoon-peak-summer'
  );

-- Weekday off-peak (seasonal)
INSERT INTO tariff_rules (component_id, day_type_id, season_id, rate, priority, metadata)
SELECT c.id, d.id, s.id, 0.74, 120, jsonb_build_object('price_key', 'g13.offPeak', 'season', s.name)
FROM tariff_components c
JOIN tariffs t ON t.id = c.tariff_id
JOIN tariff_day_types d ON d.tariff_id = t.id AND d.name = 'weekday'
JOIN tariff_seasons s ON s.tariff_id = t.id
WHERE t.name = 'Tauron G13 (2026)' AND c.name = 'Energy total'
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rules r WHERE r.component_id = c.id AND r.day_type_id = d.id AND r.season_id = s.id AND r.rate = 0.74
  );

INSERT INTO tariff_rule_windows (rule_id, start_time, end_time, label)
SELECT r.id, '00:00', '07:00', 'off-peak-night'
FROM tariff_rules r
JOIN tariff_components c ON c.id = r.component_id
JOIN tariffs t ON t.id = c.tariff_id
JOIN tariff_seasons s ON s.id = r.season_id
WHERE t.name = 'Tauron G13 (2026)' AND c.name = 'Energy total' AND r.rate = 0.74 AND s.name = 'winter'
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rule_windows w WHERE w.rule_id = r.id AND w.label = 'off-peak-night'
  );

INSERT INTO tariff_rule_windows (rule_id, start_time, end_time, label)
SELECT r.id, '13:00', '16:00', 'off-peak-midday'
FROM tariff_rules r
JOIN tariff_components c ON c.id = r.component_id
JOIN tariffs t ON t.id = c.tariff_id
JOIN tariff_seasons s ON s.id = r.season_id
WHERE t.name = 'Tauron G13 (2026)' AND c.name = 'Energy total' AND r.rate = 0.74 AND s.name = 'winter'
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rule_windows w WHERE w.rule_id = r.id AND w.label = 'off-peak-midday'
  );

INSERT INTO tariff_rule_windows (rule_id, start_time, end_time, label)
SELECT r.id, '21:00', '23:59:59', 'off-peak-late'
FROM tariff_rules r
JOIN tariff_components c ON c.id = r.component_id
JOIN tariffs t ON t.id = c.tariff_id
JOIN tariff_seasons s ON s.id = r.season_id
WHERE t.name = 'Tauron G13 (2026)' AND c.name = 'Energy total' AND r.rate = 0.74 AND s.name = 'winter'
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rule_windows w WHERE w.rule_id = r.id AND w.label = 'off-peak-late'
  );

INSERT INTO tariff_rule_windows (rule_id, start_time, end_time, label)
SELECT r.id, '00:00', '07:00', 'off-peak-night'
FROM tariff_rules r
JOIN tariff_components c ON c.id = r.component_id
JOIN tariffs t ON t.id = c.tariff_id
JOIN tariff_seasons s ON s.id = r.season_id
WHERE t.name = 'Tauron G13 (2026)' AND c.name = 'Energy total' AND r.rate = 0.74 AND s.name = 'summer'
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rule_windows w WHERE w.rule_id = r.id AND w.label = 'off-peak-night'
  );

INSERT INTO tariff_rule_windows (rule_id, start_time, end_time, label)
SELECT r.id, '13:00', '19:00', 'off-peak-midday'
FROM tariff_rules r
JOIN tariff_components c ON c.id = r.component_id
JOIN tariffs t ON t.id = c.tariff_id
JOIN tariff_seasons s ON s.id = r.season_id
WHERE t.name = 'Tauron G13 (2026)' AND c.name = 'Energy total' AND r.rate = 0.74 AND s.name = 'summer'
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rule_windows w WHERE w.rule_id = r.id AND w.label = 'off-peak-midday'
  );

INSERT INTO tariff_rule_windows (rule_id, start_time, end_time, label)
SELECT r.id, '22:00', '23:59:59', 'off-peak-late'
FROM tariff_rules r
JOIN tariff_components c ON c.id = r.component_id
JOIN tariffs t ON t.id = c.tariff_id
JOIN tariff_seasons s ON s.id = r.season_id
WHERE t.name = 'Tauron G13 (2026)' AND c.name = 'Energy total' AND r.rate = 0.74 AND s.name = 'summer'
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rule_windows w WHERE w.rule_id = r.id AND w.label = 'off-peak-late'
  );

-- Weekend off-peak (all day)
INSERT INTO tariff_rules (component_id, day_type_id, rate, priority, metadata)
SELECT c.id, d.id, 0.74, 130, jsonb_build_object('price_key', 'g13.offPeak.weekend')
FROM tariff_components c
JOIN tariffs t ON t.id = c.tariff_id
JOIN tariff_day_types d ON d.tariff_id = t.id AND d.name = 'weekend'
WHERE t.name = 'Tauron G13 (2026)' AND c.name = 'Energy total'
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rules r WHERE r.component_id = c.id AND r.day_type_id = d.id AND r.rate = 0.74
  );

INSERT INTO tariff_rule_windows (rule_id, start_time, end_time, label)
SELECT r.id, '00:00', '23:59:59', 'weekend-all-day'
FROM tariff_rules r
JOIN tariff_components c ON c.id = r.component_id
JOIN tariffs t ON t.id = c.tariff_id
JOIN tariff_day_types d ON d.id = r.day_type_id AND d.name = 'weekend'
WHERE t.name = 'Tauron G13 (2026)' AND c.name = 'Energy total' AND r.rate = 0.74
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rule_windows w WHERE w.rule_id = r.id AND w.label = 'weekend-all-day'
  );

INSERT INTO tariff_rules (component_id, rate, priority, metadata)
SELECT c.id, 31.50, 100, jsonb_build_object('price_key', 'tradeFee')
FROM tariff_components c
JOIN tariffs t ON t.id = c.tariff_id
WHERE t.name = 'Tauron G13 (2026)' AND c.name = 'Trade fee'
  AND NOT EXISTS (
      SELECT 1 FROM tariff_rules r WHERE r.component_id = c.id AND r.rate = 31.50
  );
