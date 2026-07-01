#!/usr/bin/env sh
set -eu
PGPASSWORD=evalpass pg_dump -h db -U evaluser evaldb > /backup/dump.sql
