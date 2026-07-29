# ADR-013 — Write Confirmation, Audit, and Deletion

> Chinese version: [013-write-confirmation-audit-delete.zh.md](013-write-confirmation-audit-delete.zh.md)

## Status

Accepted (2026-07-03)

## Context

[ADR-011](011-kb-access-and-org-isolation.md) / [ADR-012](012-billing-and-quotas.md) settled access and billing. Product discussion further clarified:

- Users by default have write access to **both the personal and public libraries** (one key writes to both), so **writing to the wrong library** must be avoided
- **Verifying/refuting** existing experience vs **supplementing/adding** should be treated differently
- Confirmation happens **before the write** (agent ↔ user), not "write a draft first, approve in bulk later"
- **The agent itself decides** whether user confirmation is needed; the server trusts the agent's declaration and **keeps an audit trail**
- Every library must have a **readable name** so agents can judge the target library
- Users must be able to **audit** their agents' writes and **hard-delete** their own records (including in the public library)

ADR-012's original "downgrade does not delete records" must be amended: **owners may hard-delete their own records**; the system never deletes user data due to non-payment/downgrade.

## Decision

### 1. Write types and decision tree

`ma3_report` branches by the **type the agent declares** (the server trusts the agent, backstopped by audit + deletion):

| Type | Required | Target library | Confirmation |
|------|------|--------|------|
| **Verify / refute** | `target_record_id` | **The target's library** (server-resolved; agent cannot change it) | None needed |
| **Supplement / new** | `library_id` (or default → personal library) | Agent chooses based on library **name** | See §2 |

**Verify/refute invariant**:

- Must carry `target_record_id`; the server validates the key can read that record
- Write library = `records.library_id` of target
- `confirmation = verify_direct`

### 2. Supplement/new: confirmation before write

- **No** pending draft is created; nothing lands in the DB before confirmation
- The agent confirms the target library with the user in the local conversation (showing the **library name**)
- After the user agrees, the agent sends the write request with `confirmation`
- The agent **decides on its own** whether user confirmation is needed; two legal values:
  - `user_confirmed` — confirmed with the user
  - `agent_judged` — the agent judged no confirmation was needed (e.g. fully automated scenarios)
- The server does **not** enforce interactive/autonomous key modes; it **audits the confirmation type as declared**

**Default library**: when supplement/new omits `library_id`, default to the **personal library** (fail-safe: mistaken writes land on the harmless side).

### 3. Library naming (the agent's basis for judgment)

- Every library must have a **`name`** (human-readable)
- Personal library default name: `<display_name>'s personal library`
- Public library: `Community Library`
- `ma3_context` / `ma3_whoami` / key grant listings return `{library_id, name, visibility}`

### 4. User write audit

- New tool **`ma3_list_my_writes`**: lists the current principal's write history
- Fields include: `created_at`, `key_id`, `library_id`, `library_name`, `record_id`, `confirmation`, `report_kind` (verify|supplement|new)
- Observatory **`/ui/writes/`** read-only page shows the same data
- Every successful `ma3_report` appends to **`write_audit_log`** (see design/10)

### 5. Hard delete (owner) and deletion protection (paid)

**Default (including Free personal and the public library) = hard delete, unrecoverable:**

- New tool **`ma3_delete_record(record_id)`**
- **Permission**: only the **record's writing owner** (`principal_id` match) may delete; **including in the public library**, no maintainer required
- **Effect**: payload **physically removed** from `records`, the search index, and embeddings
- **Tombstone**: the `record_deletions` table keeps `{record_id, library_id, deleted_by, deleted_at}` — **content is deleted, the deletion action leaves a trace**
- **Downstream**: **no cascading deletes**. Rows in `record_relations` pointing at a deleted record are marked `source_deleted=true`; the read path emits `lineage_warnings` saying "the evidence source has been deleted"
- **System behavior**: non-payment/downgrade does **not** auto-delete records (distinct from owner hard delete)

**Deletion protection (recycle bin / recoverable) = paid feature:**

- Only a **paid org** (Team plan billing_account) can **enable** `deletion_protection` on libraries **it owns** (org libraries)
- When enabled, `ma3_delete_record` becomes a **soft delete**: the record goes to the recycle bin (`status=trashed`, removed from search) for a **retention window** (default 30 days, configurable)
- **`ma3_restore_record(record_id)`**: within the window, the owner or an org maintainer can restore
- Window expiry or manual purge → becomes the **hard delete + tombstone** described above
- **Not enabled / non-paid / personal / public libraries**: no recycle bin; deletion is immediately hard
- This clause **refines** the [pitch.md](../../01-product/pitch.md) "humans can restore mistaken deletions" promise: **restore capability is a library-level privilege of paid orgs**; default-tier deletion is irreversible

### 6. Amendment to ADR-012

The original "downgrade/non-payment: records are not deleted" is refined to:

- Non-payment/downgrade: write limits and read-quota limits, but the system does **not** delete data  
- **Users** can delete records **they wrote** via `ma3_delete_record`  
- **Deletion protection** is a Team plan privilege (`plans.deletion_protection`); after downgrade, already-trashed records are purged per a grace policy or the user is prompted to export  

## Consequences

### Positive

- Wrong-library writes: verify/refute is structurally pinned to the library; supplement/new defaults to the personal library + agent confirmation
- Compliance: audit + user hard delete + tombstone
- Flexibility: trusts agent judgment, no forced key modes

### Negative

- Agents may misclassify or abuse `agent_judged` — relies on audit and user deletion
- Dangling downstream references after hard delete — mitigated by lineage warnings
- A public-library owner deleting a record may affect others' dependencies — accepted by product (users own their writes)
- "Delete is irreversible" at the default tier is strict for Free/personal/public users — offset by paid deletion protection; mis-delete risk mitigated by agent pre-write confirmation + audit

### Related

- [ADR-011](011-kb-access-and-org-isolation.md), [ADR-012](012-billing-and-quotas.md)
- [writes-audit-and-deletion.md](../../03-backend/writes-audit-and-deletion.md)
