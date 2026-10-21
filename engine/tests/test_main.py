import os
import subprocess
import sys

import httpx


def test_ready_line_is_connectable_and_exits_on_stdin_close(tmp_path):
    proc = subprocess.Popen(
        [sys.executable, "-m", "folio_engine", "--exit-on-stdin-close", "--data-dir", str(tmp_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        env={**os.environ, "FOLIO_ENGINE_TOKEN": "tok"},
    )
    try:
        line = proc.stdout.readline().decode().strip()
        assert line.startswith("FOLIO_ENGINE_READY port=")
        port = int(line.rsplit("=", 1)[1])
        r = httpx.get(f"http://127.0.0.1:{port}/health", headers={"Authorization": "Bearer tok"}, timeout=10)
        assert r.status_code == 200
        proc.stdin.close()
        assert proc.wait(timeout=10) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
