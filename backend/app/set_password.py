"""Set or change the login username/password from the command line.

Writes AUTH_USERNAME and AUTH_PASSWORD_HASH (never the plain password) into
the project-root `.env`. Restart the platform afterwards to pick them up.

Run from backend/:  python -m app.set_password [username]
"""

import getpass
import sys

from app.auth import hash_password
from app.ensure_key import set_env_var


def main() -> int:
    username = sys.argv[1] if len(sys.argv) > 1 else input("Username [admin]: ").strip() or "admin"
    password = getpass.getpass("New password (min 8 characters): ")
    if len(password) < 8:
        print("Password must be at least 8 characters.", file=sys.stderr)
        return 1
    if getpass.getpass("Confirm password: ") != password:
        print("Passwords do not match.", file=sys.stderr)
        return 1
    set_env_var("AUTH_USERNAME", username)
    set_env_var(
        "AUTH_PASSWORD_HASH",
        hash_password(password),
        comment=["Login credentials — change with: python -m app.set_password"],
    )
    print(f"Credentials updated for user {username!r}. Restart the platform to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
