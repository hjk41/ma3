# ma3 agent policy — eval harness

For every non-trivial task in this eval run:

1. Call **ma3_context** first with `target_product=ma3-eval` and `target_component=<scenario-id>`.
2. Treat returned records as prior lessons; verify against local files and tests.
3. After solving, if the outcome is reusable, call **ma3_validate** then **ma3_report** with `redaction_mode=auto`.
4. Do not store secrets, subscription URLs, or raw API keys in ma3 reports.

If ma3 is unavailable, continue and note it briefly.
