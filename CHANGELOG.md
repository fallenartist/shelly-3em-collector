# Changelog

## 0.1.0 - 2026-02-05
### Added
- Shelly RPC client and polling loops for live power and EMData intervals.
- PostgreSQL schema and async DB layer for readings, intervals, and alerts.
- Alert engine with threshold, sustain, and cooldown logic.
- HTTP trigger integration for Homebridge webhooks.
- Dockerfile and Docker Compose configuration for external databases.
- Health endpoint (`/healthz`) and structured JSON logging.
- README setup instructions for Pi, Docker, and Homebridge webhooks.
