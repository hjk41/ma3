# Changelog (docs index)

> Chinese version: [changelog.zh.md](changelog.zh.md)

> **Status**: to be established — record by semver starting from the first public release.
>
> Project-level changelog: [../../CHANGELOG.md](../../CHANGELOG.md).

## Format

Follow [Keep a Changelog](https://keepachangelog.com/):

- **Added** / **Changed** / **Fixed** / **Removed** / **Security**
- Link ADR or docs specs when there is a breaking change

## Unreleased

### Added

- Unified user-portal IA (top bar: Libraries · Records · Votes · API Keys)
- Write buffer (24h default; author-visible)
- API key hard delete instead of revoke
- One-time display-name setup
- MCP error message self-correction (ADR-014)
- Search GTN ranking (unified lexical path)

### Changed

- Default landing page `/ui/me/`
- Observatory for non-admin → 403
- Principal ID moved to settings (read-only)

## Still to fill in

- [ ] Version number ↔ git tag mapping
- [ ] Backfill historical versions (202 deployment milestones)
