# Billing P2 — 202 lab notes (Stripe test)

Secrets live only in `deploy/self-host/.env` (gitignored). **Rotate** any `sk_test_` that was pasted into chat.

## Enable
```
MA3_BILLING_PROVIDER=stripe
MA3_STRIPE_SECRET_KEY=sk_test_...
MA3_STRIPE_WEBHOOK_SECRET=whsec_...   # from `stripe listen`
MA3_STRIPE_PRICE_PRO=price_...
MA3_STRIPE_PRICE_TEAM=price_...
```

## Webhook forward (LAN cannot receive Stripe cloud webhooks)
```
stripe listen --forward-to http://127.0.0.1:8010/webhooks/stripe
```

## Smoke
1. Free personal BA → `/ui/billing/` shows「升级套餐」form
2. POST upgrade → 303 to `checkout.stripe.com`
3. Test card `4242 4242 4242 4242`
4. Webhook activates plan (success URL alone does not)

Default OSS self-host keeps `MA3_BILLING_PROVIDER` unset/`none`.
