import os
import subprocess
import sys

import httpx


def test_ready_line_is_connectable_and_exits_on_stdin_close(tmp_path):
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "folio_engine",
            "--exit-on-stdin-close",
            "--data-dir",
            str(tmp_path),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        env={**os.environ, "FOLIO_ENGINE_TOKEN": "tok"},
    )
    try:
        line = proc.stdout.readline().decode().strip()
        assert line.startswith("FOLIO_ENGINE_READY port=")
        port = int(line.rsplit("=", 1)[1])
        r = httpx.get(
            f"http://127.0.0.1:{port}/health",
            headers={"Authorization": "Bearer tok"},
            timeout=10,
        )
        assert r.status_code == 200
        proc.stdin.close()
        assert proc.wait(timeout=10) == 0
    finally:
        if proc.poll() is None:
            proc.kill()


def test_watch_parent_exits_when_parent_gone():
    from folio_engine.__main__ import watch_parent

    answers = iter([True, True, False])
    calls = []
    watch_parent(
        1234,
        exists=lambda pid: next(answers),
        exit_fn=lambda: calls.append(1),
        interval_s=0,
    )
    assert calls == [1]


def test_watch_parent_keeps_running():
    from folio_engine.__main__ import watch_parent

    calls = []
    watch_parent(
        1234,
        exists=lambda pid: True,
        exit_fn=lambda: calls.append(1),
        interval_s=0,
        max_checks=3,
    )
    assert calls == []


def test_main_accepts_parent_pid():
    from folio_engine.__main__ import build_parser

    args = build_parser().parse_args(["--data-dir", "x", "--parent-pid", "42"])
    assert args.parent_pid == 42


def test_watch_parent_survives_exists_error():
    from folio_engine.__main__ import watch_parent

    seq = iter([RuntimeError("boom"), False])

    def exists(pid):
        v = next(seq)
        if isinstance(v, Exception):
            raise v
        return v

    calls = []
    watch_parent(1234, exists=exists, exit_fn=lambda: calls.append(1), interval_s=0)
    assert calls == [1]


def test_engine_exits_when_parent_pid_is_dead(tmp_path):
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "folio_engine",
            "--data-dir",
            str(tmp_path),
            "--parent-pid",
            str(dead.pid),
        ],
        stdout=subprocess.PIPE,
        env={**os.environ, "FOLIO_ENGINE_TOKEN": "tok"},
    )
    try:
        assert proc.wait(timeout=10) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
