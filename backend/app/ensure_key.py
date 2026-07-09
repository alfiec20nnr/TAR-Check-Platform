"""Ensure the project-root `.env` contains an ENCRYPTION_KEY.

Personal data columns are encrypted at rest with this Fernet key. The start
scripts run this once per launch: if `.env` has no key yet, a fresh one is
generated and written in place, so a first-time install gets encryption out
of the box. An existing key is never touched — replacing it would make
previously stored data unreadable.

Run from backend/:  python -m app.ensure_key
"""

import re
import sys
from pathlib import Path

from cryptography.fernet import Fernet

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
_KEY_LINE = re.compile(r"^\s*ENCRYPTION_KEY\s*=\s*(.*?)\s*$")


def ensure_key(env_path: Path = ENV_PATH) -> bool:
    """Write a generated ENCRYPTION_KEY into *env_path* if none is set.

    Returns True when a new key was written, False when one already exists.
    """
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    # python-dotenv uses the LAST occurrence of a variable, so decide on that.
    matches = [
        (i, m.group(1).strip().strip("'\""))
        for i, line in enumerate(lines)
        if (m := _KEY_LINE.match(line))
    ]
    if matches and matches[-1][1]:
        return False  # a key is already configured — never overwrite it

    entry = f"ENCRYPTION_KEY={Fernet.generate_key().decode()}"
    if matches:
        lines[matches[-1][0]] = entry
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("# Generated automatically on first start — keep this file")
        lines.append("# with your database; without the key stored data is unreadable.")
        lines.append(entry)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def main() -> int:
    try:
        if ensure_key():
            print(
                "Generated a new ENCRYPTION_KEY in .env — personal data will be "
                "encrypted at rest. Keep .env with the database when moving or "
                "backing up."
            )
    except Exception as exc:  # noqa: BLE001 — never block startup over this
        print(f"Warning: could not check/write ENCRYPTION_KEY in .env: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
