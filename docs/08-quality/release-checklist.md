# Release Checklist

> Chinese version: [release-checklist.zh.md](release-checklist.zh.md)

> **Status**: to be completed

## Pre-release (draft)

- [ ] Full `pytest` green
- [ ] `ma3_doctor` with no failures (target environment)
- [ ] MCP smoke: `tools/list`, `ma3_whoami`, `ma3_context`, dry-run `ma3_report`
- [ ] Portal smoke: login → `/ui/me/` → keys list
- [ ] Authing callback + setup flow (new account on staging)
- [ ] Manifest / policy `skill_bundle_version` bump (if the policy changed)
- [ ] ADRs/docs consistent with behavior (if breaking)
- [ ] Acceptance P* regression (see [acceptance-criteria.md](acceptance-criteria.md))

## Post-deploy

- [ ] `/healthz` version/commit correct
- [ ] Admin can access Observatory; non-admin gets 403
- [ ] Buffer publish job running (write buffered → wait 60s → active)
- [ ] No abnormal error rate in monitoring

## To be added

- [ ] Rollback checklist items
- [ ] Database migration ordering
- [ ] Customer-visible changelog link
