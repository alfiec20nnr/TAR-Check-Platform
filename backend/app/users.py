"""Manage login accounts from the command line.

All accounts are equal (no roles), so account administration deliberately
lives here rather than in the web UI. On the hosted stack:

    docker compose exec api python -m app.users add jane.smith

Run from backend/ on a local install:  python -m app.users list

Commands:
    add <username>       create an account; prints a one-time password
    reset <username>     set a new one-time password
    disable <username>   block logins and revoke live sessions (keeps history)
    enable <username>    re-enable a disabled account
    remove <username>    delete the account (its audit trail is kept)
    list                 show all accounts

`add` and `reset` print a generated password for you to hand to the user,
who should change it from the account menu after first login.
"""

import asyncio
import logging
import secrets
import sys

from sqlalchemy import select

from app.auth import hash_password
from app.database import get_session_factory
from app.models.user import USERNAME_RE, User, normalise_username

logger = logging.getLogger(__name__)

_USAGE = __doc__.split("Commands:")[1] if __doc__ else ""


def _one_time_password() -> str:
    return secrets.token_urlsafe(12)


def _ensure_schema() -> None:
    """Bring the database up to date so the CLI works before a first launch."""
    from alembic.config import Config

    from alembic import command

    command.upgrade(Config("alembic.ini"), "head")


async def _get_user(session, username: str) -> User:
    user = (
        await session.execute(
            select(User).where(User.username == normalise_username(username))
        )
    ).scalar_one_or_none()
    if user is None:
        print(f"No account named {username!r}.", file=sys.stderr)
        raise SystemExit(1)
    return user


async def add(username: str) -> None:
    username = normalise_username(username)
    if not USERNAME_RE.fullmatch(username):
        print(
            "Username must be 3-100 characters using letters, digits, dots, "
            "dashes, underscores or @ (stored lowercase).",
            file=sys.stderr,
        )
        raise SystemExit(1)
    async with get_session_factory()() as session:
        existing = (
            await session.execute(select(User.id).where(User.username == username))
        ).first()
        if existing is not None:
            print(f"Account {username!r} already exists.", file=sys.stderr)
            raise SystemExit(1)
        password = _one_time_password()
        session.add(User(username=username, password_hash=hash_password(password)))
        await session.commit()
    print(f"Created account {username!r}.")
    print(f"One-time password: {password}")
    print("Ask the user to change it from the account menu after logging in.")


async def reset(username: str) -> None:
    async with get_session_factory()() as session:
        user = await _get_user(session, username)
        password = _one_time_password()
        user.password_hash = hash_password(password)
        await session.commit()
    print(f"Password reset for {username!r}.")
    print(f"One-time password: {password}")


async def set_active(username: str, active: bool) -> None:
    async with get_session_factory()() as session:
        user = await _get_user(session, username)
        user.is_active = active
        await session.commit()
    print(f"Account {username!r} {'enabled' if active else 'disabled'}.")


async def remove(username: str) -> None:
    async with get_session_factory()() as session:
        user = await _get_user(session, username)
        await session.delete(user)
        await session.commit()
    print(f"Removed account {username!r}. Its searches and audit entries remain.")


async def list_users() -> None:
    async with get_session_factory()() as session:
        users = (
            (await session.execute(select(User).order_by(User.username)))
            .scalars()
            .all()
        )
    if not users:
        print("No accounts yet. Create one with: python -m app.users add <username>")
        return
    for user in users:
        state = "active" if user.is_active else "DISABLED"
        last = (
            user.last_login_at.strftime("%Y-%m-%d %H:%M UTC")
            if user.last_login_at
            else "never"
        )
        print(f"{user.username:<30} {state:<9} last login: {last}")


def main() -> int:
    logging.basicConfig(level=logging.WARNING)
    args = sys.argv[1:]
    if not args:
        print(f"Usage: python -m app.users <command>\n{_USAGE}", file=sys.stderr)
        return 1
    command, *rest = args
    _ensure_schema()
    if command == "list" and not rest:
        asyncio.run(list_users())
        return 0
    if command in ("add", "reset", "disable", "enable", "remove") and len(rest) == 1:
        action = {
            "add": lambda u: add(u),
            "reset": lambda u: reset(u),
            "disable": lambda u: set_active(u, False),
            "enable": lambda u: set_active(u, True),
            "remove": lambda u: remove(u),
        }[command]
        asyncio.run(action(rest[0]))
        return 0
    print(f"Usage: python -m app.users <command>\n{_USAGE}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
