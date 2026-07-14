from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

from scripts.secure_secret_file import secure_write_text


def test_secure_write_text_replaces_content_without_inherited_permissions(tmp_path: Path):
    target = tmp_path / "handoff.txt"
    secure_write_text(target, "synthetic-only\n")

    assert target.read_text(encoding="utf-8") == "synthetic-only\n"
    if os.name == "nt":
        acl = subprocess.run(
            ["icacls", str(target)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        assert "(I)" not in acl
    else:
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
