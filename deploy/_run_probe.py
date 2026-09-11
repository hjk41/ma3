from pathlib import Path
import subprocess
import sys

src = Path(r"C:\doc\ma3\deploy\_probe_202_to_ma3io.sh")
dst = Path("/tmp/_probe_202_to_ma3io.sh")
# When run under WSL python, use linux paths
try:
    wsl_src = Path("/mnt/c/doc/ma3/deploy/_probe_202_to_ma3io.sh")
    if wsl_src.exists():
        src = wsl_src
except Exception:
    pass

data = src.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
# Write via WSL
subprocess.check_call(["wsl", "-e", "bash", "-lc", f"cat > /tmp/_probe_202_to_ma3io.sh <<'EOF'\n{data.decode()}\nEOF\nchmod +x /tmp/_probe_202_to_ma3io.sh"])
subprocess.check_call(["wsl", "-e", "bash", "-lc", "scp -i $HOME/.ssh/id_rsa -o ConnectTimeout=10 /tmp/_probe_202_to_ma3io.sh hct@192.168.31.202:/tmp/_probe_202_to_ma3io.sh"])
subprocess.check_call(["wsl", "-e", "bash", "-lc", "ssh -i $HOME/.ssh/id_rsa -o ConnectTimeout=10 hct@192.168.31.202 bash /tmp/_probe_202_to_ma3io.sh"])
