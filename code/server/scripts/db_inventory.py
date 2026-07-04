#!/usr/bin/env python3
"""Snapshot PostgreSQL ma3 inventory for deploy before/after checks."""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import psycopg
from psycopg.rows import dict_row


def _table_exists(conn: psycopg.Connection, name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (name,),
    ).fetchone()
    return row is not None


def _count(conn: psycopg.Connection, table: str, *, where: str = "", params: tuple[Any, ...] = ()) -> int:
    sql = f"SELECT COUNT(*) AS c FROM {table}"
    if where:
        sql += f" WHERE {where}"
    row = conn.execute(sql, params).fetchone()
    return int(row["c"]) if row else 0


def collect_inventory(database_url: str) -> dict[str, Any]:
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        inv: dict[str, Any] = {
            "database": "postgresql",
            "v1_records": _count(conn, "records"),
            "v1_active": _count(conn, "records", where="status = %s", params=("active",)),
            "v1_cases": _count(conn, "cases"),
            "legacy_records": 0,
            "legacy_active": 0,
            "legacy_cases": 0,
            "legacy_importable": 0,
            "legacy_overlap_v1": 0,
            "legacy_seed_skipped": 0,
        }
        if _table_exists(conn, "legacy_records"):
            inv["legacy_records"] = _count(conn, "legacy_records")
            inv["legacy_active"] = _count(conn, "legacy_records", where="status = %s", params=("active",))
            inv["legacy_seed_skipped"] = _count(
                conn, "legacy_records", where="id LIKE %s", params=("vk_seed_%",)
            )
            inv["legacy_overlap_v1"] = _count(
                conn,
                "legacy_records lr",
                where="EXISTS (SELECT 1 FROM records r WHERE r.id = lr.id)",
            )
            inv["legacy_importable"] = _count(
                conn,
                "legacy_records lr",
                where="lr.id NOT LIKE %s AND NOT EXISTS (SELECT 1 FROM records r WHERE r.id = lr.id)",
                params=("vk_seed_%",),
            )
        if _table_exists(conn, "legacy_cases"):
            inv["legacy_cases"] = _count(conn, "legacy_cases")
        return inv


def compare_inventory(
    pre: dict[str, Any],
    post: dict[str, Any],
    *,
    backfill: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    if post["v1_records"] < pre["v1_records"]:
        errors.append(
            f"v1 records decreased: {pre['v1_records']} -> {post['v1_records']}"
        )
    importable = int(pre.get("legacy_importable") or 0)
    if importable > 0:
        expected_min = pre["v1_records"] + importable
        if post["v1_records"] < expected_min:
            errors.append(
                f"after backfill expected >= {expected_min} v1 records "
                f"(pre {pre['v1_records']} + legacy_importable {importable}), got {post['v1_records']}"
            )
        if backfill is not None:
            imported = int(backfill.get("records_imported") or 0)
            if imported < importable:
                errors.append(
                    f"backfill imported {imported} records but {importable} were importable"
                )
    if int(pre.get("legacy_records") or 0) > 0 and int(post.get("legacy_importable") or 0) > 0:
        errors.append(
            f"legacy_importable still {post['legacy_importable']} after deploy; expected 0"
        )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="ma3 DB inventory snapshot/compare")
    parser.add_argument("--compare", metavar="PRE_JSON", help="Compare current DB against a prior snapshot")
    parser.add_argument("--backfill", metavar="JSON", help="Backfill result JSON from migrate_legacy_pg.py")
    parser.add_argument("-o", "--output", metavar="FILE", help="Write snapshot JSON to file")
    args = parser.parse_args()

    database_url = os.environ.get("MA3_DATABASE_URL")
    if not database_url or not database_url.startswith("postgresql"):
        print("Set MA3_DATABASE_URL to a postgresql URL", file=sys.stderr)
        return 1

    inv = collect_inventory(database_url)
    backfill = None
    if args.backfill:
        with open(args.backfill, encoding="utf-8") as fh:
            backfill = json.load(fh)

    if args.compare:
        with open(args.compare, encoding="utf-8") as fh:
            pre = json.load(fh)
        errors = compare_inventory(pre, inv, backfill=backfill)
        report = {"pre": pre, "post": inv, "backfill": backfill, "ok": not errors}
        if args.output:
            with open(args.output, "w", encoding="utf-8") as fh:
                json.dump(inv, fh, indent=2)
                fh.write("\n")
        print(json.dumps(report, indent=2))
        for err in errors:
            print(f"INVENTORY CHECK FAIL: {err}", file=sys.stderr)
        if errors:
            return 1
        print("INVENTORY CHECK OK")
        return 0

    payload = json.dumps(inv, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.write("\n")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
