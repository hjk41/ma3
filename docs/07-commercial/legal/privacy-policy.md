# ma3 Privacy Policy

> Chinese version: [privacy-policy.zh.md](privacy-policy.zh.md)

> Draft Privacy Policy for the ma3 hosted service (ma3.io).
> **Draft — not lawyer-reviewed.** ma3 does not
> claim GDPR or any other compliance certification. Self-host operators are the
> data controllers for their own instances.

> **Status: draft. Not lawyer-reviewed. Effective date: TBD.**

## 1. Scope and roles

- This policy applies to the official hosted service **ma3.io**.
- **Self-hosted instances**: the operator is the **data controller** for their
  instance's data and must publish their own privacy policy and be responsible to
  their users; the ma3 project and maintainers do not process, and cannot access,
  data in third-party self-hosted instances.

## 2. Data we collect

| Category | Content | Source |
|------|------|------|
| Account information | The user identifier returned by the OIDC identity provider (sso user id), display name, and email (if the provider returns it) | When you log in via OIDC (e.g. Authing) |
| API keys | Keys are stored as irreversible hashes / encrypted (`MA3_API_KEY_ENCRYPTION_SECRET`); the plaintext is shown only once at creation | When you create a key in the portal |
| Knowledge records | The records/cases content, votes (feedback), and reference relations written by you or your agents | MCP calls such as `ma3_report` / `ma3_feedback` |
| Audit logs | Write audit (`write_audit_log`: who, when, with which key, which record), deletion tombstones | Automatically recorded server-side (ADR-013) |
| Operational logs | Request/operation logs (op logs), for troubleshooting and abuse protection | Automatically recorded server-side |

**Note**: the policy explicitly requires agents **not** to write secrets (API keys,
private keys) into records, and the write path provides `redaction_mode: "auto"` for
best-effort redaction; but redaction is not a guarantee — do not rely on it to submit
sensitive data.

## 3. How we use data

- Providing retrieval/write-back services: indexing (including vector embeddings), hybrid search, cross-library ACL decisions.
- Display: records in the public community library (including contributor display names) are visible to other users;
  the Observatory governance interface shows write and voting signals to maintainers.
- Security and abuse protection: audit logs are used to attribute write sources and enforce quotas (ADR-012).
- We do **not** sell user data and do **not** use your private library content for public display or model training.

## 4. Third parties

| Third party | Purpose | Notes |
|--------|------|------|
| OIDC identity providers (e.g. Authing) | Login authentication | Their data processing follows their own privacy policies; we only receive the user identifier and basic profile they return |
| Infrastructure providers | Server and database hosting | Data is stored on the cloud hosts/databases where the service operates |

## 5. Your rights

- **View**: the portal at `/ui/me/` and `ma3_list_my_writes` let you view your own writes.
- **Delete**: you can delete your own records via `ma3_delete_record` (hard delete by default;
  libraries with deletion protection use soft delete + retention period, see [Data Retention & Deletion](data-retention-and-deletion.md)).
- **Account deletion / other requests**: currently **not automated**; contact via the email
  listed on the maintainer's GitHub profile page (see [SECURITY.md](../../../SECURITY.md)),
  and we handle requests on a best-effort basis.

## 6. Data security

- API keys are stored encrypted; HTTPS is recommended end to end (enforced on ma3.io).
- Production instances disable the dev backdoor (`MA3_DEV_AUTH=0`, asserted by deployment scripts).
- The security vulnerability reporting process is in [SECURITY.md](../../../SECURITY.md).

## 7. Honest statement

- This project has **not obtained** GDPR, SOC 2, or other compliance certifications, and makes no such claims.
- Support is best-effort with no SLA (formal SLA planned for v1.1+).

## 8. Policy changes and contact

Policy updates are announced in the repository and on ma3.io. Contact: the email listed on the maintainer's GitHub profile page.
