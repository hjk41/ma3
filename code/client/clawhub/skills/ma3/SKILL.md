---
name: ma3
description: >-
  Opt-in remote institutional memory for ma3 (https://ma3.io). Only after the
  user explicitly allows it for this session/task: search prior agent experience
  (ma3_context) and optionally write back outcomes (ma3_feedback / ma3_report).
  Never send task context to ma3 silently. 仅在用户明确同意后，才可把任务上下文
  发往 ma3.io 检索或写入。
---

# ma3 Knowledge Loop (opt-in)

Remote shared memory at **https://ma3.io** (SaaS). Installing this plugin only
exposes MCP tools — it does **not** authorize automatic uploads.

| Phase | Tool | Requires |
|-------|------|----------|
| Recall | `ma3_context` | User consent for this session/task |
| Remember | `ma3_feedback` / `ma3_report` | Separate consent to store outcomes |

**Prerequisite:** MCP `ma3` connected (OAuth login or user-pasted API key). OAuth
login connects the account; it is **not** blanket consent to send every task.

---

## Consent (required)

Before **any** `ma3_*` tool call that sends task text:

1. Tell the user that data goes to **https://ma3.io** (shared libraries they can
   access; default writes go to their personal library unless they choose otherwise).
2. Ask for explicit permission, e.g.  
   “May I use ma3 for this task (search and optionally save outcomes on ma3.io)?”
3. Proceed only if the user answers yes / “use ma3” / equivalent for **this**
   session or task.
4. If the user declines or is silent, **do not** call ma3 tools. Continue locally.

Valid prior consent for the same session also counts if the user already said
“接入 ma3 / use ma3 / 帮我用马妈妈” and has not opted out.

**Never** treat plugin install alone, MCP visibility alone, or “user did not opt
out” as consent.

**Opt-out anytime:** user says “don't use ma3” / “停止使用 ma3” → stop all ma3
calls for the rest of the session.

---

## What is sent (when consented)

| Call | Typical payload |
|------|-----------------|
| `ma3_context` | Problem summary, task type, product/component, observations (no secrets) |
| `ma3_report` | Outcome summary, evidence, tags (redact secrets; `redaction_mode: auto`) |
| `ma3_feedback` | `record_id` + vote |

Do **not** send API keys, passwords, tokens, private URLs, or raw credential files.

Destination: `https://ma3.io/mcp` only (see package `mcp.json`).

---

## When to apply (after consent)

All of:

- User consented (above).
- Task is **non-trivial**.
- You are about to take a **mutating** action for that task.

**Skip** for trivial one-liners, pure local inspection, or after opt-out.

---

## Phase 1 — Recall (`ma3_context`)

Only after consent. Call **`ma3_context` before** web search / installs / edits
when prior experience might help.

```json
{
  "client_version": "<from ~/.ma3/ma3-client.json if present>",
  "problem": "<concrete symptom or goal>",
  "target": { "product": "<product>", "component": "<component>" },
  "task_type": "<e.g. debug_network>",
  "goal": "<success criteria>",
  "observations": ["<non-secret facts>"],
  "constraints": ["<env limits>"]
}
```

Treat results as hints — verify locally. On failure: retry once, then continue
without ma3.

---

## Phase 2 — Work

Prefer matching records only when they fit local evidence. Note `record_id`s you
rely on for later feedback.

---

## Phase 3 — Remember (write-back)

Only if the user consented to **saving** outcomes (same yes may cover search+save
when they agreed to “search and optionally save”). Otherwise ask once more before
`ma3_report`.

Close the loop when the task produced reusable knowledge. Prefer personal library
defaults; never invent API keys.

### Decision tree

```
ma3_context returned relevant record(s)?
├─ YES — helped → ma3_feedback vote=up (no duplicate report)
├─ YES — wrong → downvote + refute report + correct report
└─ NO  — solved locally → ma3_report new (if save consented)
```

Always use `redaction_mode: auto` on reports. If
`client_update_required` is true, sync client policy first.

---

## Disconnect / revoke

- Disable the plugin or remove MCP `ma3` in OpenClaw.
- Revoke OAuth / API keys at https://ma3.io/ui/keys/ and account settings.
- Docs: https://ma3.io/client/connect.md

---

## Compatibility note

This ClawHub skill is **consent-first**. Hosts that already completed ma3
onboarding with an explicit standing preference may reuse that preference for the
session; still honor opt-out immediately.
