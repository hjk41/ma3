#!/usr/bin/env bash
set -euo pipefail
tr -d '\r' < /mnt/c/doc/ma3/deploy/_probe_202_to_ma3io.sh > /tmp/_probe_202_to_ma3io.sh
scp -i "$HOME/.ssh/id_rsa" -o ConnectTimeout=10 /tmp/_probe_202_to_ma3io.sh hct@192.168.31.202:/tmp/_probe_202_to_ma3io.sh
ssh -i "$HOME/.ssh/id_rsa" -o ConnectTimeout=10 hct@192.168.31.202 bash /tmp/_probe_202_to_ma3io.sh
