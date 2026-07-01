#!/bin/sh
# Broken: wrong hostname and output path
pg_dump -h localhost -U wronguser evaldb > /tmp/dump.sql
