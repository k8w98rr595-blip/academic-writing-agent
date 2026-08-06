from __future__ import annotations

import argparse
import getpass
import re
from pathlib import Path

from argon2 import PasswordHasher

try:
    from .secure_secret_file import secure_write_text
except ImportError:  # Direct script execution keeps the scripts directory on sys.path.
    from secure_secret_file import secure_write_text


PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


def validate_password_strength(password: str) -> None:
    if len(password) < 16 or len(password) > 256:
        raise ValueError("Password must contain between 16 and 256 characters")
    if any(character.isspace() for character in password):
        raise ValueError("Password must not contain whitespace")
    categories = (
        re.search(r"[a-z]", password),
        re.search(r"[A-Z]", password),
        re.search(r"[0-9]", password),
        re.search(r"[^A-Za-z0-9]", password),
    )
    if not all(categories):
        raise ValueError("Password must include lowercase, uppercase, number, and symbol characters")


def create_password_verifier(password: str, confirmation: str) -> str:
    if password != confirmation:
        raise ValueError("Password confirmation does not match")
    validate_password_strength(password)
    return PASSWORD_HASHER.hash(password)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create an ACL-restricted Argon2id owner-password verifier without storing plaintext."
    )
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output", default="data/owner-password-hash.txt")
    parser.add_argument("--force", action="store_true", help="Replace the existing verifier file")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    output = (root / args.output).resolve()
    try:
        output.relative_to(root)
    except ValueError:
        parser.error("Output must stay inside the project root")
    if output.exists() and not args.force:
        parser.error(f"Verifier file already exists: {output}. No value was changed.")

    password = getpass.getpass("New Paperlight owner password: ")
    confirmation = getpass.getpass("Confirm new owner password: ")
    try:
        verifier = create_password_verifier(password, confirmation)
    except ValueError as error:
        parser.error(str(error))
    finally:
        password = ""
        confirmation = ""

    secure_write_text(output, f"OWNER_PASSWORD_HASH={verifier}\n")
    print(f"Created an ACL-restricted verifier file: {output}")
    print("No plaintext password or TOTP material was written or displayed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
