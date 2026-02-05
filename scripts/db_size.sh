#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is not set. Load .env first:" >&2
  echo "  set -a; source .env; set +a" >&2
  exit 1
fi

psql "$DATABASE_URL" <<'SQL'
SELECT pg_size_pretty(pg_database_size(current_database())) AS db_size;

SELECT
  relname,
  pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_catalog.pg_statio_user_tables
WHERE relname IN ('power_readings', 'power_readings_1m')
ORDER BY pg_total_relation_size(relid) DESC;
SQL
