#!/usr/bin/env bash
# File design-backlog B1–B4 as GitHub Issues and rewrite docs/09-engineering/design-backlog.md with links.
# Requires: gh auth login (repo scope)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI not found; install then: gh auth login" >&2
  exit 1
fi
if ! gh auth status >/dev/null 2>&1; then
  echo "Not logged in. Run: gh auth login" >&2
  exit 1
fi

create_one() {
  local title="$1"
  local body="$2"
  local label="$3"
  gh issue create --title "$title" --label "$label" --body "$body"
}

# Labels may not exist yet — create best-effort
gh label create "design" --description "Design / ADR backlog" --color "5319E7" 2>/dev/null || true
gh label create "enhancement" --color "a2eeef" 2>/dev/null || true

B1_URL=$(create_one \
  "design(B1): maintainer / compliance deletion of others' content" \
  "$(cat <<'EOF'
## Context
Migrated from `docs/09-engineering/design-backlog.md` (B1 / former T1).

Pitch promises humans/team maintainers can clear privacy / values / compliance-violating content — especially **records others wrote in the public library**.

## Gap
- ADR-013 covers **owner deletes own** records only
- No maintainer takedown, privacy deletion request, or legal hold
- Current takedown is manual email (see `docs/07-commercial/legal/data-retention-and-deletion.md`)

## Design together
- SLA / first-class audit
- Org force-private / ban writes to community library
- Audit export / retention policy

## Output
New ADR (number TBD; 014/015 taken) + design doc.

**Not a delivery commitment** until design is ratified.
EOF
)" "design")

B2_URL=$(create_one \
  "design(B2): automated maintainer Agent" \
  "$(cat <<'EOF'
## Context
Migrated from `docs/09-engineering/design-backlog.md` (B2 / former T2).

Pitch headline: maintainer Agent does scaled day-to-day maintenance (stale detection / organize / summarize). Currently roadmap-only, no design.

## Need to define
- Staleness signals
- Auto supersede / organize boundaries
- Human correction loop
- Misjudgment metrics

**Not a delivery commitment** until design is ratified.
EOF
)" "design")

B3_URL=$(create_one \
  "design(B3): org members / SSO / SCIM / seats" \
  "$(cat <<'EOF'
## Context
Migrated from `docs/09-engineering/design-backlog.md` (B3 / former T3).

ADR-011 says admin manages members and Team has 5 seats, but invite flow (partially shipped), seat allocation, and SSO/SCIM provisioning still need design. Pitch calls out SSO for v1.1+.

**Not a delivery commitment** until design is ratified.
EOF
)" "design")

B4_URL=$(create_one \
  "design(B4): integrator / delegated sub-identity (B2B2C)" \
  "$(cat <<'EOF'
## Context
Migrated from `docs/09-engineering/design-backlog.md` (B4 / former T4).

Persona review: integrator apps hold keys and act as delegated sub-identities for end customers. No priority or design yet.

**Not a delivery commitment** until design is ratified.
EOF
)" "design")

echo "Created:"
echo "  B1 $B1_URL"
echo "  B2 $B2_URL"
echo "  B3 $B3_URL"
echo "  B4 $B4_URL"

# Rewrite backlog with links
cat > docs/09-engineering/design-backlog.md <<EOF
# 设计 Backlog（design backlog）

> 来源：原仓库根 \`todo.md\`（2026-07-03 pitch vs PITCH.md 缺口评审）迁移至此。
> 这些是**计划中的设计议题（planned design issues），不是承诺（not commitments）**——
> 无排期、无交付承诺，讨论定稿后才会转为 ADR / design 文档。
>
> **真源**：以下 GitHub Issues（本文件仅作索引）。

## 待设计议题

| ID | Issue | 摘要 |
|----|-------|------|
| B1 | $B1_URL | 维护者/合规删除他人内容 |
| B2 | $B2_URL | 自动维护者 Agent |
| B3 | $B3_URL | Org 成员 / SSO / SCIM / seats |
| B4 | $B4_URL | Integrator / 委托子身份（B2B2C） |

重新建 Issue：\`bash scripts/file_design_backlog_issues.sh\`（会新建而非去重，慎用）。

## 已决策（追溯用，已落文档）

- **防误删 = 付费功能**：仅付费 org 可对其**拥有**的库开启（回收站/恢复）；默认硬删不可恢复。→ ADR-013 / design-10
- **所有读写都需 key**：移除匿名读表述，全文档同步。→ ADR-011 + pitch/design 同步
- **不强制一把 key 只对应一个库**：跨库/跨 org 由企业行政手段解决，服务端不强隔离。→ ADR-011 备注
- **库容量超额 → 只读**：超 cap 后该库禁写、可读。→ ADR-012 / design-09
EOF

echo "Updated docs/09-engineering/design-backlog.md"
