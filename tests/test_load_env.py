"""scripts/vast/load_env.sh must survive a secrets file saved in Windows Notepad.

Runs the real script under bash. Skipped where bash is not available (Windows).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
LOAD_ENV = REPO / "scripts" / "vast" / "load_env.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def _load(tmp_path: Path, content: bytes, *names: str, strict: bool = False) -> dict:
    """Write ~/.cctv.env, source load_env.sh in a fresh bash, return the vars."""
    home = tmp_path / "home"
    home.mkdir()
    (home / ".cctv.env").write_bytes(content)
    prefix = "set -euo pipefail; " if strict else ""
    script = prefix + f". {LOAD_ENV}; " + "; ".join(
        f'printf "%s=[%s]\\n" {n} "${{{n}:-}}"' for n in names
    )
    out = subprocess.run(
        ["bash", "-c", script],
        env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    values = {}
    for line in out.splitlines():
        key, _, rest = line.partition("=")
        values[key] = rest[1:-1]  # strip the [ ] guards
    return values


def test_windows_notepad_file_with_bom_and_crlf(tmp_path):
    content = (
        "﻿GH_TOKEN=github_pat_ABC123\r\n"
        "RCLONE_CONFIG_B2_TYPE=b2\r\n"
        "RCLONE_CONFIG_B2_ACCOUNT=004abc0000000001\r\n"
        "RCLONE_CONFIG_B2_KEY=K004xyz/+abc\r\n"
        "B2_REMOTE=b2:cctv-idle-data\r\n"
    ).encode("utf-8")
    got = _load(
        tmp_path, content, "GH_TOKEN", "RCLONE_CONFIG_B2_TYPE",
        "RCLONE_CONFIG_B2_ACCOUNT", "RCLONE_CONFIG_B2_KEY", "B2_REMOTE",
    )
    # No trailing \r and no BOM glued onto the first key.
    assert got == {
        "GH_TOKEN": "github_pat_ABC123",
        "RCLONE_CONFIG_B2_TYPE": "b2",
        "RCLONE_CONFIG_B2_ACCOUNT": "004abc0000000001",
        "RCLONE_CONFIG_B2_KEY": "K004xyz/+abc",
        "B2_REMOTE": "b2:cctv-idle-data",
    }


def test_export_prefix_comments_and_blank_lines(tmp_path):
    content = b"# my secrets\n\nexport GH_TOKEN=abc\n   B2_REMOTE=b2:x\nnot a line\n"
    got = _load(tmp_path, content, "GH_TOKEN", "B2_REMOTE")
    assert got == {"GH_TOKEN": "abc", "B2_REMOTE": "b2:x"}


def test_clean_copy_is_private(tmp_path):
    _load(tmp_path, b"GH_TOKEN=abc\n", "GH_TOKEN")
    clean = tmp_path / "home" / ".cctv.env.sh"
    assert clean.exists()
    assert oct(clean.stat().st_mode & 0o777) == "0o600"


def test_empty_file_does_not_kill_a_strict_caller(tmp_path):
    """save_run.sh runs with set -euo pipefail; an empty file must not abort it."""
    got = _load(tmp_path, b"# nothing yet\n", "GH_TOKEN", strict=True)
    assert got == {"GH_TOKEN": ""}


def test_missing_file_is_a_no_op(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    out = subprocess.run(
        ["bash", "-c", f"set -euo pipefail; . {LOAD_ENV}; echo ok"],
        env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True, check=True,
    ).stdout
    assert out.strip() == "ok"
    assert not (home / ".cctv.env.sh").exists()
