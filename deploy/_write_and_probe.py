#!/usr/bin/env python3
from pathlib import Path
import subprocess

src = Path("/mnt/c/doc/ma3/deploy/_probe_202_to_ma3io.sh")
body = src.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
Path("/tmp/_probe_202_to_ma3io.sh").write_bytes(body)
subprocess.check_call(
    [
        "scp",
        "-i",
        str(Path.home() / ".ssh" / "id_rsa"),
        "-o",
        "ConnectTimeout=10",
        "/tmp/_probe_202_to_ma3io.sh",
        "hct@192.168.31.202:/tmp/_probe_202_to_ma3io.sh",
    ]
)
subprocess.check_call(
    [
        "ssh",
        "-i",
        str(Path.home() / ".ssh" / "id_rsa"),
        "-o",
        "ConnectTimeout=10",
        "hct@192.168.31.202",
        "bash",
        "/tmp/_probe_202_to_ma3io.sh",
    ]
)
