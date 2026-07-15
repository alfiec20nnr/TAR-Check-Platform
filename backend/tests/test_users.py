"""Account management: the app.users CLI and the .env → users-table migration."""

import pytest
from sqlalchemy import delete, select

from app import users as users_cli
from app.auth import verify_password
from app.database import get_session_factory
from app.models import User
from app.seed import seed_default_user


async def _all_usernames() -> list[str]:
    async with get_session_factory()() as session:
        return list(
            (await session.execute(select(User.username).order_by(User.username))).scalars()
        )


async def _get_user(username: str) -> User:
    async with get_session_factory()() as session:
        return (
            await session.execute(select(User).where(User.username == username))
        ).scalar_one()


def _printed_password(capsys) -> str:
    out = capsys.readouterr().out
    line = next(line for line in out.splitlines() if line.startswith("One-time password:"))
    return line.split(":", 1)[1].strip()


# --- CLI ------------------------------------------------------------------------


async def test_add_creates_account_with_one_time_password(capsys):
    await users_cli.add("Jane.Smith")  # normalised to lowercase
    password = _printed_password(capsys)
    user = await _get_user("jane.smith")
    assert user.is_active
    assert verify_password(password, user.password_hash)


async def test_add_rejects_duplicate_and_invalid_usernames(capsys):
    await users_cli.add("jane.smith")
    with pytest.raises(SystemExit):
        await users_cli.add("jane.smith")
    with pytest.raises(SystemExit):
        await users_cli.add("bad user!")
    with pytest.raises(SystemExit):
        await users_cli.add("ab")  # too short
    # Colons are excluded — the username is embedded in the session payload.
    with pytest.raises(SystemExit):
        await users_cli.add("jane:smith")


async def test_reset_changes_password(capsys):
    await users_cli.add("jane.smith")
    first = _printed_password(capsys)
    await users_cli.reset("jane.smith")
    second = _printed_password(capsys)
    user = await _get_user("jane.smith")
    assert not verify_password(first, user.password_hash)
    assert verify_password(second, user.password_hash)


async def test_disable_enable_and_remove(capsys):
    await users_cli.add("jane.smith")
    await users_cli.set_active("jane.smith", False)
    assert not (await _get_user("jane.smith")).is_active
    await users_cli.set_active("jane.smith", True)
    assert (await _get_user("jane.smith")).is_active
    await users_cli.remove("jane.smith")
    assert "jane.smith" not in await _all_usernames()


async def test_commands_fail_cleanly_for_unknown_user():
    with pytest.raises(SystemExit):
        await users_cli.reset("nobody")
    with pytest.raises(SystemExit):
        await users_cli.remove("nobody")


# --- Legacy .env migration --------------------------------------------------------


async def test_seed_default_user_is_idempotent():
    # conftest's _prepare_db already ran the migration once (user: admin).
    assert await _all_usernames() == ["admin"]
    await seed_default_user()
    assert await _all_usernames() == ["admin"]


async def test_seed_default_user_skips_when_accounts_exist(capsys):
    async with get_session_factory()() as session:
        await session.execute(delete(User))
        await session.commit()
    await users_cli.add("jane.smith")
    await seed_default_user()  # legacy hash set, but an account already exists
    assert await _all_usernames() == ["jane.smith"]


async def test_seed_default_user_no_op_without_legacy_credentials(settings, monkeypatch):
    monkeypatch.setattr(settings, "auth_password_hash", "")
    async with get_session_factory()() as session:
        await session.execute(delete(User))
        await session.commit()
    await seed_default_user()
    assert await _all_usernames() == []
