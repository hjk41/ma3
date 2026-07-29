# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Self-host local auth, first-run setup, portal REST (orgs/libraries/admin), org invites & member aliases
- Public legal draft docs under `docs/07-commercial/legal/`
- GitHub Actions CI (unit, integration, **integration-postgres**, self-host Docker build)
- `CONTRIBUTING.md`, Issue/PR templates, English README gateway
- `scripts/file_design_backlog_issues.sh` to turn design backlog into GitHub Issues
- Phase 0 off-host uptime probe: `deploy/observability/probe_ma3.sh` (+ systemd examples)

### Changed

- **Docs language policy:** English is the default for `README.md` and `docs/**/*.md`; Chinese retained as sibling `*.zh.md` files (former `README.en.md` removed)
- Observability decisions ratified for issue #5 (metrics off by default on self-host; same-host Prometheus later; webhook paging; internal SLO-1–3 first) — see `docs/09-engineering/design-archive/25-metrics-slo-decisions.md`

### Support posture

- All tiers: community **best-effort**, **no SLA** today; formal SLA remains a v1.1+ planning item for paid tiers
