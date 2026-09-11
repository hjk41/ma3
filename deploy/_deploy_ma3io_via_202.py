#!/usr/bin/env python3
"""Push Windows deploy.ma3.io.env to 202 and run deploy from ma3_deploy -> ma3.io."""
from __future__ import annotations

import subprocess
from pathlib import Path

HOME_KEY = str(Path.home() / ".ssh" / "id_rsa")
HOST202 = "hct@192.168.31.202"


def sh(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd)


def lf_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def main() -> None:
    # 1) Stage LF-normalized deploy.sh + ma3.io env onto 202
    deploy_sh = lf_bytes(Path("/mnt/c/doc/ma3/deploy/deploy.sh"))
    env_io = lf_bytes(Path("/mnt/c/doc/ma3/deploy/deploy.ma3.io.env"))
    Path("/tmp/deploy.sh.lf").write_bytes(deploy_sh)
    Path("/tmp/deploy.ma3.io.env.lf").write_bytes(env_io)

    remote_helper = r'''#!/usr/bin/env bash
set -euo pipefail
REPO=/home/hct/ma3_deploy
WRAP=$(mktemp -d /tmp/ma3_io_wrap.XXXXXX)
trap 'rm -rf "$WRAP"' EXIT

# Use runtime tree as rsync source (already has latest code from LAN deploy).
install -m 0755 /tmp/deploy.sh.lf "$WRAP/deploy.sh"
install -m 0644 /tmp/deploy.ma3.io.env.lf "$WRAP/deploy.ma3.io.env"

# Point SCRIPT_DIR/REPO_DIR at the runtime checkout on 202.
sed -i "s|^SCRIPT_DIR=.*|SCRIPT_DIR=${REPO}/deploy|" "$WRAP/deploy.sh"
sed -i "s|^REPO_DIR=.*|REPO_DIR=${REPO}|" "$WRAP/deploy.sh"

# Ensure shell scripts under runtime deploy/ are LF (in case prior Windows rsync left CRLF).
find "${REPO}/deploy" -type f \( -name '*.sh' -o -name '*.bash' \) -print0 \
  | while IFS= read -r -d '' f; do
      tr -d '\r' < "$f" > "$f.lf" && mv "$f.lf" "$f"
    done

export SSH_KEY="${HOME}/.ssh/id_rsa"
echo "==> from $(hostname): deploy ${REPO} -> ma3.io"
bash "$WRAP/deploy.sh" "$WRAP/deploy.ma3.io.env"
'''
    Path("/tmp/remote_deploy_ma3io.sh").write_text(remote_helper, encoding="utf-8", newline="\n")

    scp = ["scp", "-i", HOME_KEY, "-o", "ConnectTimeout=15"]
    ssh = ["ssh", "-i", HOME_KEY, "-o", "ConnectTimeout=15", HOST202]
    sh(scp + ["/tmp/deploy.sh.lf", f"{HOST202}:/tmp/deploy.sh.lf"])
    sh(scp + ["/tmp/deploy.ma3.io.env.lf", f"{HOST202}:/tmp/deploy.ma3.io.env.lf"])
    sh(scp + ["/tmp/remote_deploy_ma3io.sh", f"{HOST202}:/tmp/remote_deploy_ma3io.sh"])
    sh(ssh + ["bash", "/tmp/remote_deploy_ma3io.sh"])


if __name__ == "__main__":
    main()
