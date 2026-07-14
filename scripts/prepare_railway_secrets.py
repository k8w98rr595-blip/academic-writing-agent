from __future__ import annotations

import argparse
import secrets
from pathlib import Path

import pyotp
from argon2 import PasswordHasher

from secure_secret_file import secure_write_text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    target = root / "data" / "railway-owner.txt"
    if target.exists() and not args.force:
        print(f"Railway owner handoff already exists: {target}")
        print("No secrets were changed.")
        return
    email = "owner@paperlight.local"
    password = f"Pl-{secrets.token_urlsafe(22)}"
    totp_secret = pyotp.random_base32()
    password_hash = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2).hash(password)
    target.parent.mkdir(parents=True, exist_ok=True)
    secure_write_text(
        target,
        "Paperlight Railway owner handoff\n"
        "This ignored file is not part of Git. Save the login values in a password manager, configure the Railway variables, then delete it.\n\n"
        f"OWNER_EMAIL={email}\n"
        f"OWNER_PASSWORD_HASH={password_hash}\n"
        f"OWNER_TOTP_SECRET={totp_secret}\n"
        "REQUIRE_TOTP=1\n\n"
        f"Login password: {password}\n"
        f"TOTP URI: {pyotp.TOTP(totp_secret).provisioning_uri(name=email, issuer_name='Paperlight')}\n",
    )
    print(f"Created ignored Railway owner handoff: {target}")
    print("Secret values were not printed.")


if __name__ == "__main__":
    main()
