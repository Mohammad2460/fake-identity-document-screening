"""run.sh is the one-command cold start. These are source-level checks only —
the test suite must never actually start the venv/server (that would be slow,
network-dependent, and would block on uvicorn's exec).
"""
import os
import re

RUN_SH = os.path.join(os.path.dirname(__file__), "..", "run.sh")


def _read() -> str:
    with open(RUN_SH, encoding="utf-8") as fh:
        return fh.read()


def test_run_sh_exists():
    assert os.path.isfile(RUN_SH)


def test_run_sh_is_executable():
    assert os.access(RUN_SH, os.X_OK)


def test_run_sh_is_strict_bash():
    text = _read()
    assert text.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in text


def test_run_sh_checks_python3_present():
    text = _read()
    assert "command -v python3" in text


def test_run_sh_creates_venv_if_missing():
    text = _read()
    assert "python3 -m venv .venv" in text
    assert "[ ! -d .venv ]" in text


def test_run_sh_installs_requirements():
    text = _read()
    assert "./.venv/bin/pip install" in text
    assert "-r requirements.txt" in text


def test_run_sh_downloads_models_once():
    text = _read()
    assert "scripts.download_models" in text


def test_run_sh_fetches_faces_once():
    text = _read()
    assert "scripts.fetch_faces" in text


def test_run_sh_generates_samples_once():
    text = _read()
    assert "scripts.make_samples" in text


def test_run_sh_starts_uvicorn_on_port_8000():
    text = _read()
    assert "uvicorn app.main:app" in text
    assert "--port 8000" in text


def test_run_sh_command_sequence_is_documented_order():
    """venv -> deps -> models -> faces -> samples -> server, in that order."""
    text = _read()
    markers = [
        "python3 -m venv .venv",
        "pip install",
        "scripts.download_models",
        "scripts.fetch_faces",
        "scripts.make_samples",
        "uvicorn app.main:app",
    ]
    positions = [text.index(m) for m in markers]
    assert positions == sorted(positions), "run.sh steps are out of order"


def test_run_sh_uses_exec_for_server_so_it_becomes_pid1():
    text = _read()
    assert re.search(r"^exec \./\.venv/bin/uvicorn", text, re.MULTILINE)
