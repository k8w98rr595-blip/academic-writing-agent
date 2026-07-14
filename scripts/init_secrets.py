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
    parser.add_argument("--force", action="store_true", help="Replace an existing local secret file")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    env_file = root / ".env.local"
    if env_file.exists() and not args.force:
        print(f"Local configuration already exists: {env_file}")
        print("No secrets were changed. Pass --force only when intentional credential rotation is required.")
        return
    example = (root / ".env.example").read_text(encoding="utf-8")
    email = "owner@paperlight.local"
    password = f"Pl-{secrets.token_urlsafe(18)}"
    totp_secret = pyotp.random_base32()
    password_hash = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2).hash(password)
    values = {
        "OWNER_EMAIL": email,
        "OWNER_PASSWORD_HASH": password_hash,
        "OWNER_TOTP_SECRET": totp_secret,
        "REQUIRE_TOTP": "1",
    }
    output = []
    for line in example.splitlines():
        key = line.split("=", 1)[0] if "=" in line else ""
        output.append(f"{key}={values[key]}" if key in values else line)
    secure_write_text(env_file, "\n".join(output) + "\n")
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    bootstrap = (
        "Paperlight local owner credentials\n"
        "Keep this ignored file private and delete it after saving the values in a password manager.\n\n"
        f"Email: {email}\n"
        f"Password: {password}\n"
        f"TOTP secret: {totp_secret}\n"
        f"TOTP URI: {pyotp.TOTP(totp_secret).provisioning_uri(name=email, issuer_name='Paperlight Local')}\n"
    )
    credentials = data_dir / "bootstrap-owner.txt"
    secure_write_text(credentials, bootstrap)
    print(f"Created ignored local configuration: {env_file}")
    print(f"Created ignored owner handoff: {credentials}")
    print("Secret values were not printed.")


if __name__ == "__main__":
    main()
