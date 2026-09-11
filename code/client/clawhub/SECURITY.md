# Security & privacy (ma3 ClawHub bundle)

## Disclosure

This package connects OpenClaw to a **remote** service:

- Endpoint: `https://ma3.io/mcp` (Streamable HTTP)
- Purpose: institutional memory search (`ma3_context`) and optional write-back
  (`ma3_feedback`, `ma3_report`)
- No API keys or secrets are bundled. Auth is user OAuth or a user-pasted portal key.

## Consent model

| Gate | Meaning |
|------|---------|
| Install plugin | Exposes tools only; **no** network memory calls by itself |
| OAuth / API key | Account authentication; **not** blanket per-task upload consent |
| Skill consent | Agent must obtain **explicit user permission** before sending task context |
| Opt-out | “don't use ma3” stops further calls in the session |

Skill instructions (`skills/ma3/SKILL.md`) forbid silent uploads.

## Data minimization

- Send problem summaries and outcomes, not secrets.
- Reports use server-side `redaction_mode: auto`.
- Default writes target the user's personal library unless they choose otherwise.

## Revocation

- Remove MCP / disable plugin in OpenClaw.
- Revoke keys at https://ma3.io/ui/keys/
- Account controls at https://ma3.io/ui/me/

## Source

- Repository: https://github.com/hjk41/ma3
- Package path: `code/client/clawhub`
