"""Set or change a login password from the command line.

Updates the account in the users table (creating it if it does not exist
yet). Kept as the command local install docs reference; `python -m app.users`
offers fuller account management (list/disable/remove, generated one-time
passwords).

Run from backend/:  python -m app.set_password [username]
"""

import asyncio
import getpass
import sys

from sqlalchemy import select

from app.auth import hash_password
from app.database import get_session_factory
from app.models.user import USERNAME_RE, User, normalise_username
from app.users import _ensure_schema


async def _set_password(username: str, password_hash: str) -> bool:
    """Update (or create) the account; returns True when newly created."""
    async with get_session_factory()() as session:
        user = (
            await session.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()
        if user is None:
            session.add(User(username=username, password_hash=password_hash))
        else:
            user.password_hash = password_hash
        await session.commit()
        return user is None


def main() -> int:
    raw = sys.argv[1] if len(sys.argv) > 1 else input("Username [admin]: ").strip() or "admin"
    username = normalise_username(raw)
    if not USERNAME_RE.fullmatch(username):
        print(
            "Username must be 3-100 characters using letters, digits, dots, "
            "dashes, underscores or @.",
            file=sys.stderr,
        )
        return 1
    password = getpass.getpass("New password (min 8 characters): ")
    if len(password) < 8:
        print("Password must be at least 8 characters.", file=sys.stderr)
        return 1
    if getpass.getpass("Confirm password: ") != password:
        print("Passwords do not match.", file=sys.stderr)
        return 1
    _ensure_schema()
    created = asyncio.run(_set_password(username, hash_password(password)))
    verb = "created" if created else "updated"
    print(f"Account {username!r} {verb}. The new password applies immediately.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
