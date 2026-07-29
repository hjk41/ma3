# UI Copy and Interaction Conventions

> Chinese version: [ui-copy-and-interactions.zh.md](ui-copy-and-interactions.zh.md)

> **Status**: to be completed — the following are the finalized fragments so far

## Top Bar and Navigation

| Location | Copy | Notes |
|------|------|------|
| Top bar | Home · Libraries · Records · Votes · API Keys | Do not literally borrow the English word "Libraries" for the Chinese label |
| subnav (`/ui/me/*` only) | Overview · Settings | Does not include "My contributions / My votes" |
| admin | Observatory | English; `.nav-admin` de-emphasized |

## List Page Titles

| Route | h1 |
|------|-----|
| `/ui/me/writes/` | Records |
| `/ui/me/votes/` | Votes |
| `/ui/libraries/` | Libraries |

## API Keys

| Element | Copy |
|------|------|
| Delete button | Delete |
| Delete title | Once deleted, this key stops working immediately and cannot be recovered. |
| Quota error | active key limit reached; delete an old key first |
| Legacy key without ciphertext | This legacy key has no stored copy; to copy the full key, create a new key and delete the old one. |

**Forbidden**: "revoke" / "revoked"

## 403 / Empty States

| Scenario | Copy |
|------|------|
| Observatory 403 | Observatory is accessible only to product administrators. + link "Back to my home" |
| New user with no contributions | Guide to create an API key → onboarding |
| Anonymous public library | CTA "Sign in to contribute and vote" |

## Interaction Patterns

- Delete: `onsubmit="return confirm(...)"` (list and detail danger-zone)
- Copy: `ma3CopyFrom(this)` + `.copy-src` input immediately before the button
- Form failure: SSR re-render, refilling user input (keys detail edit)
- No toast / modal framework (v1)

## To Be Completed

- [ ] Site-wide error page templates (401/403/404/503)
- [ ] Inline copy for form validation errors
- [ ] Chinese/English mixed-text conventions (exception list of terms Observatory keeps in English)
