# ADR-014 — MCP Errors Must Be Self-Correctable

> Chinese version: [014-mcp-error-self-correction.zh.md](014-mcp-error-self-correction.zh.md)

## Status

Accepted (2026-07-03)

## Context

ma3 v1's agent surface is MCP only ([ADR-003](003-mcp-only-agent-surface.md)). The agent is the **sole** consumer and mostly runs **unattended** — whatever error it reads is what it bases its next step on.

A real evaluation exposed a systemic flaw:

- The server **already** put structured diagnostics (`validation_errors`, `schema_hint`, field paths) into JSON-RPC `error.data`.
- But **MCP hosts (Cursor / Claude Code, etc.) only hand `error.message` to the model**; `error.data` is often dropped — the **same class** of host behavior as the earlier `structuredContent` invisibility finding.
- Result: Claude mistakenly wrapped the `ma3_report` payload inside `arguments` (copying `ma3_validate`'s `{tool_name, arguments}` envelope), received `-32602 "Invalid params"` (no field info), **retried the same mistake 6 times**, then gave up without writing back.

In other words: "the information exists in the protocol, but not where the agent can see it."

## Decision

**Constraint (invariant)**: **every MCP error must carry, in `error.message`, enough information for the agent to correct itself.**

Specifically:

1. `error.message` is the **only** field that can be assumed to reach the model. Anything the agent needs for self-correction (which field is missing, what is extraneous, what shape is expected, how to obtain permission) **must** appear in `message`.
2. `error.data` still keeps a structured copy (`validation_errors`, `status_code`, `schema_hint`, etc.) for programmatic clients that can read data — but it **must not** be the **only** carrier of self-correction information.
3. For validation errors (`-32602` / `-32600`), the message must explain missing / unexpected / type errors **field by field**, and give a **targeted hint** when a common misuse is detected (e.g. wrapping a tool payload inside `arguments`).
4. The message **must not** leak secrets, internal stack traces, SQL, or raw exception chains.

Details in [error-handling.md](../../05-agent/error-handling.md).

## Consequences

### Positive

- Unattended agents can correct themselves in one step, reducing "retry the same error until giving up / not writing back".
- Improves write-back rate and knowledge base quality (agents no longer discard reusable conclusions because `ma3_report` errored).
- The error contract becomes testable and regression-proof.

### Negative

- Messages get longer, partially duplicating `data`.
- Requires one centralized place to construct messages (`routes_mcp.py`); new error paths must obey the constraint (backed by tests).

### Related

- [ADR-003](003-mcp-only-agent-surface.md): MCP is the only agent surface → the error surface is the product surface.
- Reuses the conclusion from the `structuredContent` visibility fix: put critical information in fields the host is guaranteed to display.
