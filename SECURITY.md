# Security Policy

## Supported versions

Security fixes are applied on a best-effort basis to the default `main` branch of this repository. There is **no SLA**.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security-sensitive reports.

Email the maintainer at the address listed on the GitHub profile for [hjk41](https://github.com/hjk41), with subject line starting with `[ma3 security]`.

Include:

- Affected version / commit
- Deployment mode (SaaS, self-host Compose, etc.)
- Reproduction steps and impact

We will try to acknowledge receipt and coordinate a fix or disclosure timeline. Community support remains best-effort.

## Self-host operators

- Rotate `MA3_API_KEY_ENCRYPTION_SECRET` and bootstrap API keys if leaked
- Keep `MA3_DEV_AUTH=0` on any network-exposed instance
- Prefer HTTPS (reverse proxy) when enabling OIDC or public access
