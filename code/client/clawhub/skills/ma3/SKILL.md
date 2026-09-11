---
name: ma3
description: >-
  Query ma3 for prior agent experience before complex tasks and write back
  outcomes when done (upvote useful records, downvote wrong ones, report new
  successes or confirmed dead ends). Use for non-trivial debugging, infra fixes,
  multi-step implementation, or whenever ma3 MCP tools are visible. 复杂任务前
  检索 ma3 经验，完成后 upvote/downvote/ma3_report 回报。
---

# ma3 Knowledge Loop

Like a **memory skill** (recall → work → remember), but backed by the shared ma3
knowledge base instead of a private session file.

| Phase | Memory analogy | ma3 tool |
|-------|----------------|----------|
| Before work | Recall | `ma3_context` |
| During work | Track what you used | Note `record_id`s from context |
| After work | Remember | `ma3_feedback` and/or `ma3_report` |

**Prerequisite:** ma3 MCP is configured and visible. Read versions from
`~/.ma3/ma3-client.json` (`client_version` = `skill_bundle_version`). If MCP is
missing, skip this skill and tell the user once.

---

## When to apply

Apply this skill when **all** are true:

- The task is **non-trivial** (debugging, infra, multi-file change, unfamiliar stack).
- The user did **not** opt out of ma3.
- You are about to take a **mutating** action (edit, install, restart, web fetch for the task).

**Skip** for trivial one-liners, pure read-only inspection (`ls`, `git status`), or when
the user says "don't use ma3".

---

## Phase 1 — Recall (`ma3_context`)

Call **`ma3_context` before** web search, installs, config edits, or file writes.

Minimum payload:

```json
{
  "client_version": "<from ~/.ma3/ma3-client.json>",
  "problem": "<concrete symptom or goal>",
  "target": { "product": "<product>", "component": "<component>" },
  "task_type": "<e.g. debug_network, implement_feature>",
  "goal": "<what success looks like>",
  "observations": ["<what you already know>"],
  "constraints": ["<env limits>"]
}
```

After the call:

1. Read `structuredContent.server` for upgrade flags (`client_update_required` blocks writes).
2. **Record every returned `record_id`** you might rely on.
3. Treat records as hints — **verify locally** before applying.

If `ma3_context` fails: retry once, note unavailability, continue from local evidence.

---

## Phase 2 — Work

While executing:

- Prefer fixes from returned records when they match local evidence.
- If a record's advice **does not match** reality, stop following it and note why.
- Keep the **retrieval order** from `ma3_context` — it matters for downvotes (Phase 3).

---

## Phase 3 — Remember (write-back)

Close the loop **before ending the turn** when the task produced reusable knowledge
(success, refutation, or a confirmed dead end).

Check `structuredContent.server.client_update_required` — if `true`, run
`bash ~/.ma3/bin/sync_ma3_client.sh sync`, reload MCP, and retry until false.
(`ma3_feedback` is not version-gated; `ma3_report` is.)

### Decision tree (stop at first match)

```
ma3_context returned relevant record(s)?
├─ YES — record matched reality and helped resolve the task
│         → Case 1: upvote only (no duplicate report)
├─ YES — record was wrong / inapplicable / contradicted by evidence
│         → Case 2: downvote + refute + report correct knowledge
└─ NO  — you solved it yourself or explored dead ends
          → Case 3: report success and/or confirmed failures
```

---

### Case 1 — Experience was useful → upvote

**When:** `ma3_context` returned a record whose fix/answer you applied and it worked.

**Action:** `ma3_feedback` only — do **not** write a near-duplicate `ma3_report`.

```json
{
  "record_id": "vk_...",
  "vote": "up"
}
```

Also **downvote every wrong record ranked above** the correct one in context results
(rank-based rule from ma3 policy).

---

### Case 2 — Experience was wrong → downvote + correct report

**When:** `ma3_context` returned a record you tried or judged misleading; reality differs.

**Actions (in order):**

1. **`ma3_feedback`** `{ "record_id": "<wrong id>", "vote": "down" }` for each wrong
   record ranked **above** the correct answer (or all misleading records if none were correct).
2. **`ma3_report`** `report_kind: "refute"` with `target_record_id: "<wrong id>"` explaining
   why it fails and what actually works.
3. **`ma3_report`** `report_kind: "new"` (or `verify` if close variant) with the **correct**
   fix — only if not already covered by an existing good record you upvoted.

Refute payload sketch:

```json
{
  "client_version": "...",
  "report_kind": "refute",
  "target_record_id": "vk_wrong...",
  "problem": "<same problem domain>",
  "outcome": "resolved",
  "result_summary": "Record vk_... suggested X but Y was required because ...",
  "based_on_record_ids": ["vk_wrong..."]
}
```

New/correct knowledge payload sketch:

```json
{
  "client_version": "...",
  "report_kind": "new",
  "problem": "<concrete problem>",
  "outcome": "resolved",
  "result_summary": "<actionable fix in 1-3 sentences>",
  "actions": [{ "action": "...", "rationale": "..." }],
  "evidence": [{ "kind": "command", "summary": "..." }],
  "based_on_record_ids": ["vk_wrong..."]
}
```

---

### Case 3 — No relevant experience → report what you learned

**When:** `ma3_context` returned nothing useful (empty, unrelated, or all misleading with
no correct record).

**Report two kinds of knowledge separately when both apply:**

#### 3a — Successful resolution

```json
{
  "report_kind": "new",
  "outcome": "resolved",
  "problem": "<what was broken or needed>",
  "result_summary": "<root cause + fix future agents can reuse>"
}
```

#### 3b — Confirmed failed exploration (dead end)

Write when you **verified** an approach does not work (not mere guesses).

```json
{
  "report_kind": "new",
  "outcome": "failed",
  "problem": "<what you tried to solve>",
  "result_summary": "Tried <approach>; failed because <evidence>. Use <alternative> instead.",
  "not_applicable_if": ["<when this dead-end advice would mislead>"]
}
```

If context returned misleading records with no correct one, **downvote** those misleading
records before writing the new fix (same rank rule as Case 2).

---

## Writing records (`ma3_report`)

Before any report:

1. Call **`ma3_whoami`** if you have not inspected libraries this session.
2. Choose **`library_id`**:
   - Reusable community lessons → `lib_default`
   - Personal / host-specific / secrets-adjacent → your `kind: "personal"` library
3. Build the full payload (`redaction_mode: "auto"` — no secrets, no huge logs).
4. **`ma3_validate`** with `tool_name: "ma3_report"` and `arguments: <full flat payload>`.
   Payload is **flat** — not wrapped in `{ "tool_name", "arguments" }`.
5. **`ma3_report`** with the same payload + `client_version`.

`confirmation` is optional (`agent_judged` default). Do not ask the user to confirm in CI.

---

## End-of-task checklist

```
- [ ] ma3_context called before first mutating action (or opt-out noted)
- [ ] client_version passed; upgrade flags checked
- [ ] Useful record → ma3_feedback upvote (not duplicate report)
- [ ] Wrong records above the correct answer → downvoted
- [ ] Wrong record → refute + new correct knowledge (Case 2)
- [ ] No prior knowledge → new record(s) for success and/or dead ends (Case 3)
- [ ] ma3_validate passed before ma3_report
```

---

## Examples

### Case 1 — Proxy fix already in KB

- Context returns `vk_abc` with mihomo `allow-lan` fix.
- You apply it; `curl` succeeds.
- Write-back: `ma3_feedback { record_id: "vk_abc", vote: "up" }` only.

### Case 2 — Stale nginx advice

- Context returns `vk_old` suggesting `http3` directive on stock nginx.
- Local test: `nginx -t` fails — package has no http3 module.
- Write-back: downvote `vk_old`, refute it, `report_kind: "new"` with quic module install path.

### Case 3 — Greenfield debug

- Context returns no matching records.
- You fix a Docker DNS issue via `extra_hosts`.
- Write-back: one `report_kind: "new"`, `outcome: "resolved"`.
- You also confirmed `links:` alone did not fix it.
- Optional second record: `outcome: "failed"` documenting the dead end.

---

## Install (once per agent)

```bash
# Project-local (team shares via repo)
mkdir -p .cursor/skills
cp -r <ma3-repo>/code/client/skills/ma3 .cursor/skills/

# Or global
mkdir -p ~/.cursor/skills
cp -r <ma3-repo>/code/client/skills/ma3 ~/.cursor/skills/
```

MCP + policy setup: `GET /client/connect.md` (short) or `/client/agent-onboarding.md` on your `MA3_BASE_URL`.
