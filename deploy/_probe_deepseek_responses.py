#!/usr/bin/env python3
import json, os, urllib.request

key = os.environ["DEEPSEEK_API_KEY"]
payload = {"model": "deepseek-flash", "input": "say hi", "max_output_tokens": 16}
req = urllib.request.Request(
    "https://api.deepseek.com/v1/responses",
    data=json.dumps(payload).encode(),
    headers={
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    },
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=45) as r:
        print("responses_ok", r.status)
        print(r.read()[:400].decode("utf-8", "replace"))
except Exception as e:
    print("responses_err", type(e).__name__, e)
    if hasattr(e, "read"):
        try:
            print(e.read()[:500].decode("utf-8", "replace"))
        except Exception:
            pass
