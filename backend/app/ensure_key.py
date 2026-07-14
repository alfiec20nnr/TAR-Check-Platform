"""Ensure the project-root `.env` contains the generated secrets.

Personal data columns are encrypted at rest with ENCRYPTION_KEY, and login
session cookies are signed with AUTH_SECRET. The start scripts run this once
per launch: any secret missing from `.env` is generated and written in place,
so a first-time install gets both out of the box. An existing value is never
touched — replacing the encryption key would make previously stored data
unreadable (replacing the auth secret would merely log everyone out).

Run from backend/:  python -m app.ensure_key
"""

import re
import secrets
import sys
from pathlib import Path

from cryptography.fernet import Fernet

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def _var_line(name: str) -> re.Pattern[str]:
    return re.compile(rf"^\s*{name}\s*=\s*(.*?)\s*$")


def set_env_var(name: str, value: str, env_path: Path = ENV_PATH,
                comment: list[str] | None = None) -> None:
    """Set *name* to *value* in *env_path*, replacing any existing entry.

    python-dotenv uses the LAST occurrence of a variable, so that is the one
    replaced. *comment* lines are only written when the variable is new.
    """
    pattern = _var_line(name)
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    matches = [i for i, line in enumerate(lines) if pattern.match(line)]
    entry = f"{name}={value}"
    if matches:
        lines[matches[-1]] = entry
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(f"# {c}" for c in (comment or []))
        lines.append(entry)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _ensure_var(name: str, generate, comment: list[str],
                env_path: Path = ENV_PATH) -> bool:
    """Write a generated value for *name* into *env_path* if none is set.

    Returns True when a new value was written, False when one already exists.
    """
    pattern = _var_line(name)
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    values = [
        m.group(1).strip().strip("'\"")
        for line in lines
        if (m := pattern.match(line))
    ]
    if values and values[-1]:
        return False  # already configured — never overwrite
    set_env_var(name, generate(), env_path, comment)
    return True


def ensure_key(env_path: Path = ENV_PATH) -> bool:
    """Ensure ENCRYPTION_KEY and AUTH_SECRET exist in *env_path*.

    Returns True when a new ENCRYPTION_KEY was written (the message that
    matters to the user), False when one already exists.
    """
    wrote_key = _ensure_var(
        "ENCRYPTION_KEY",
        lambda: Fernet.generate_key().decode(),
        [
            "Generated automatically on first start — keep this file",
            "with your database; without the key stored data is unreadable.",
        ],
        env_path,
    )
    _ensure_var(
        "AUTH_SECRET",
        lambda: secrets.token_urlsafe(32),
        ["Signs login session cookies — generated automatically."],
        env_path,
    )
    return wrote_key


def main() -> int:
    try:
        if ensure_key():
            print(
                "Generated a new ENCRYPTION_KEY in .env — personal data will be "
                "encrypted at rest. Keep .env with the database when moving or "
                "backing up."
            )
    except Exception as exc:  # noqa: BLE001 — never block startup over this
        print(f"Warning: could not check/write secrets in .env: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
