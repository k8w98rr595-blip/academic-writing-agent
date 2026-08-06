from __future__ import annotations

import sys

import pytest
from argon2 import PasswordHasher

from scripts import hash_owner_password as helper


STRONG_PASSWORD = "Paperlight-Rotation-42!"


@pytest.mark.parametrize(
    "candidate",
    ["short", "alllowercasebutlong42!", "ALLUPPERCASEBUTLONG42!", "NoDigitsArePresent!", "NoSymbolIsPresent42"],
)
def test_password_helper_rejects_weak_values(candidate: str):
    with pytest.raises(ValueError):
        helper.create_password_verifier(candidate, candidate)


def test_password_helper_rejects_mismatch():
    with pytest.raises(ValueError, match="does not match"):
        helper.create_password_verifier(STRONG_PASSWORD, STRONG_PASSWORD + "x")


def test_password_helper_creates_argon2id_verifier():
    verifier = helper.create_password_verifier(STRONG_PASSWORD, STRONG_PASSWORD)
    assert verifier.startswith("$argon2id$")
    assert STRONG_PASSWORD not in verifier
    assert PasswordHasher().verify(verifier, STRONG_PASSWORD)


def test_password_helper_main_never_outputs_or_writes_plaintext(monkeypatch, tmp_path, capsys):
    captured_write: dict[str, str] = {}
    answers = iter([STRONG_PASSWORD, STRONG_PASSWORD])
    monkeypatch.setattr(helper.getpass, "getpass", lambda _: next(answers))
    monkeypatch.setattr(
        helper,
        "secure_write_text",
        lambda path, content: captured_write.update({"path": str(path), "content": content}),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["hash_owner_password.py", "--project-root", str(tmp_path)],
    )
    assert helper.main() == 0
    output = capsys.readouterr().out
    assert STRONG_PASSWORD not in output
    assert STRONG_PASSWORD not in captured_write["content"]
    assert "OWNER_PASSWORD_HASH=$argon2id$" in captured_write["content"]
    assert "TOTP" not in captured_write["content"]


def test_password_helper_refuses_existing_file_without_force(monkeypatch, tmp_path, capsys):
    target = tmp_path / "data" / "owner-password-hash.txt"
    target.parent.mkdir()
    target.write_text("existing", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["hash_owner_password.py", "--project-root", str(tmp_path)],
    )
    with pytest.raises(SystemExit):
        helper.main()
    assert target.read_text(encoding="utf-8") == "existing"
    assert "already exists" in capsys.readouterr().err
