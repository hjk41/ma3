#!/usr/bin/env python3
from pathlib import Path
import subprocess

script = r'''#!/usr/bin/env bash
set -euo pipefail
echo "HOST=$(hostname)"
which codex || true
codex --version 2>/dev/null || true
ls -la ~/.codex 2>/dev/null | head -30 || true
echo '--- config.toml ---'
sed -n '1,120p' ~/.codex/config.toml 2>/dev/null || echo 'no config.toml'
echo '--- auth/env hints ---'
grep -nEi 'deepseek|model|openai|api' ~/.codex/config.toml 2>/dev/null | head -40 || true
env | grep -Ei 'DEEPSEEK|OPENAI|CODEX' | sed 's/=.*/=<redacted>/' || true
'''
Path('/tmp/codex_probe_202.sh').write_text(script, encoding='utf-8', newline='\n')
key = str(Path.home() / '.ssh' / 'id_rsa')
subprocess.check_call(['scp', '-i', key, '-o', 'ConnectTimeout=10', '/tmp/codex_probe_202.sh', 'hct@192.168.31.202:/tmp/codex_probe_202.sh'])
subprocess.check_call(['ssh', '-i', key, '-o', 'ConnectTimeout=10', 'hct@192.168.31.202', 'bash', '/tmp/codex_probe_202.sh'])
