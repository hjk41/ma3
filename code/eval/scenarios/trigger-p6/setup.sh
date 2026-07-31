#!/usr/bin/env bash
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
ROOT="$D/workspace/sample-project"
mkdir -p "$ROOT/src" "$ROOT/tests"
cat > "$ROOT/README.md" <<'EOF'
# Sample Project

Minimal layout for trigger-p6 read-only exploration eval.
EOF
cat > "$ROOT/src/app.py" <<'EOF'
def main():
    print("hello")


if __name__ == "__main__":
    main()
EOF
cat > "$ROOT/tests/test_app.py" <<'EOF'
from src.app import main


def test_main(capsys):
    main()
    assert "hello" in capsys.readouterr().out
EOF
