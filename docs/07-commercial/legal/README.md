# Legal Documents Index

> Chinese version: [README.zh.md](README.zh.md)

> This folder contains draft legal documents for the ma3 project
> (Terms of Service, Privacy Policy, Data Retention & Deletion). English is the
> default language; Chinese versions are kept as `*.zh.md` siblings. **All
> documents here are drafts and have NOT been reviewed by a lawyer.** They
> describe the project's actual current behavior honestly (best-effort support,
> no SLA yet) and must be legally reviewed before being presented as binding
> contracts.

> **Status: draft. Not lawyer-reviewed; does not constitute legal advice. Legal review is required before formal commercial use.**

## Document list

| Document | Content |
|------|------|
| [terms-of-service.md](terms-of-service.md) | Terms of Service: service scope, accounts and API keys, rights and obligations around content and knowledge records, disclaimers |
| [privacy-policy.md](privacy-policy.md) | Privacy Policy: what data is collected, how it is used, third parties (e.g. OIDC/Authing), responsibility split for self-hosted instances |
| [data-retention-and-deletion.md](data-retention-and-deletion.md) | Data retention and deletion: record deletion (ADR-013), audit logs, backups, takedown process |

## Scope and responsibility split (important)

- **ma3.io (official SaaS)**: operated by the ma3 maintainers; the documents in this folder apply directly.
- **Self-hosted instances**: the operator is the **data controller** for their instance's data
  and must fulfill compliance obligations toward their own users; the documents here may only
  serve as template references, and the ma3 project and maintainers are not responsible for
  the data processing behavior of third-party self-hosted instances.

## Honest statement of current status

- Support for all tiers (including paid) is currently **best-effort, with no formal SLA** (formal SLA planned for v1.1+).
- Record owners can self-service delete their own records (see [ADR-013](../../02-architecture/decisions/013-write-confirmation-audit-delete.md)).
- The maintainer takedown process is **not yet automated**: contact via the email listed on the
  maintainer's GitHub profile page (see the repo root [SECURITY.md](../../../SECURITY.md)).
- This project does **not claim** GDPR or any other compliance certification.
