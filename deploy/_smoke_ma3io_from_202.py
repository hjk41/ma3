#!/usr/bin/env python3
from pathlib import Path
import subprocess

script = """#!/usr/bin/env bash
set -euo pipefail
curl -fsS --max-time 20 https://ma3.io/healthz
echo
curl -fsS --max-time 20 https://ma3.io/client/connect.md | head -n 2
echo
curl -fsS --max-time 20 https://ma3.io/.well-known/oauth-protected-resource
echo
curl -fsS --max-time 20 https://ma3.io/mcp/info
echo
"""
Path("/tmp/smoke_ma3io.sh").write_text(script, encoding="utf-8", newline="\n")
key = str(Path.home() / ".ssh" / "id_rsa")
subprocess.check_call(["scp", "-i", key, "-o", "ConnectTimeout=10", "/tmp/smoke_ma3io.sh", "hct@192.168.31.202:/tmp/smoke_ma3io.sh"])
subprocess.check_call(["ssh", "-i", key, "-o", "ConnectTimeout=10", "hct@192.168.31.202", "bash", "/tmp/smoke_ma3io.sh"])
