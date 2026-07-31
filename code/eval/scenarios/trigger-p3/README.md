# trigger-p3 — nginx http3 directive (P3)

KB must **not** contain a hit for this exact nginx 1.24 + `http3` error. Agent should read (empty),
fix config, then `ma3_report` with `report_kind: new`.

## Broken state

nginx config uses invalid `http3 on;` directive — nginx exits on start.

## Verify

```bash
bash setup.sh && bash verify.sh
```
