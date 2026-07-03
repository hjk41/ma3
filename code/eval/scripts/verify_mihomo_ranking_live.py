#!/usr/bin/env python3
"""Live mihomo search-ranking verification on the 202 host (lexical/GTN path)."""
from __future__ import annotations

import os
import sys

from fastapi.testclient import TestClient

from app.core.config import settings
from app.storage import db

search_records = db.search_records

GOLDEN_FIX = "vk_0dc976edbe9b"
QUERY = "mihomo proxy docker"
LIB_IDS = {"lib_default", "lib_7e1dbe7d8688", "lib_549ee90d2fb9"}
LIMIT = 10


def main() -> int:
    records, _ = search_records(LIB_IDS, QUERY, limit=LIMIT, explain=True)
    print(f"disable_embeddings={settings.disable_embeddings} hide_wrong={settings.search_hide_clearly_wrong}")
    print(f"hits={len(records)} query={QUERY!r}")

    ids: list[str] = []
    for i, r in enumerate(records):
        rid = str(r["id"])
        ids.append(rid)
        prob = (r.get("problem") or "")[:70].replace("\n", " ")
        rank = r.get("_rank") or {}
        print(
            f"  {i + 1}. {rid}  rel={rank.get('relevance')} final={rank.get('final_score')} "
            f"label={rank.get('label')}  {prob}"
        )

    if GOLDEN_FIX in ids:
        print(f"\nPASS: golden fix {GOLDEN_FIX} at rank {ids.index(GOLDEN_FIX) + 1}")
    else:
        print(f"\nNOTE: golden {GOLDEN_FIX} not in top-{LIMIT}")

    strong = [
        r
        for r in records
        if "mihomo" in (r.get("problem") or "").lower()
        and "proxy" in (r.get("problem") or "").lower()
    ]
    weak = [
        r
        for r in records
        if "policy" in (r.get("problem") or "").lower()
        and "mihomo" not in (r.get("problem") or "").lower()
    ]
    if strong and weak:
        s_idx = ids.index(str(strong[0]["id"]))
        w_idx = ids.index(str(weak[0]["id"]))
        if s_idx >= w_idx:
            print(f"FAIL: strong ({strong[0]['id']}) at {s_idx + 1} should beat weak ({weak[0]['id']}) at {w_idx + 1}")
            return 1
        print(f"PASS: strong mihomo ({strong[0]['id']}) ranks above policy noise ({weak[0]['id']})")
    elif strong:
        print("PASS: mihomo-relevant records in top-k (no policy-noise pair to compare)")
    else:
        print("WARN: no strong mihomo+proxy hits in top-k")

    from app.main import app

    key = os.environ.get("MA3_DEV_API_KEY", "ma3dev")
    with TestClient(app) as client:
        resp = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "ma3_context",
                    "arguments": {"problem": QUERY, "max_cases": 5, "max_records_per_case": 3},
                },
            },
            headers={"X-API-Key": key},
        )
        body = resp.json()
        if "error" in body:
            print(f"FAIL: ma3_context error: {body['error']}")
            return 1
        sc = body["result"]["structuredContent"]
        if "explain" in sc:
            print("FAIL: explain leaked in ma3_context")
            return 1
        for group in sc.get("cases", []):
            for rec in group.get("records", []):
                if "rank" in rec or "_rank" in rec:
                    print(f"FAIL: rank leaked in record keys: {rec.keys()}")
                    return 1
    print("PASS: ma3_context has no explain/rank keys")
    return 0


if __name__ == "__main__":
    sys.exit(main())
