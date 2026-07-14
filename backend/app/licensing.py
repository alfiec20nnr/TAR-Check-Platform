"""Machine activation: the platform only runs on machines the provider approves.

On an unactivated machine the UI shows a *machine code* (derived from the
operating system's stable machine identifier) and asks for an *activation
code*. Activation codes are Ed25519 signatures of the machine code, issued by
the provider's private key — which is never shipped with the application, so
codes for new machines cannot be produced by anyone else. Only the public key
below is embedded here, for verification.

This is a deterrent against casual copying, not DRM: the application ships as
readable source, so it cannot stop a determined technical user. It stops a
copied folder from simply starting on another computer.
"""

import base64
import hashlib
import logging
import platform
import subprocess
import uuid
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.config import get_settings

logger = logging.getLogger(__name__)

# Verification half of the provider's licensing keypair (the private half
# lives only on the provider's own machine).
PUBLIC_KEY_HEX = "7ec25e968a74685a7695870465901c98f0091ad392696767abf73363c6c2435d"


def _raw_machine_id() -> str:
    """A stable per-OS-install identifier (survives reboots, not reinstalls)."""
    system = platform.system()
    try:
        if system == "Windows":
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
            ) as key:
                return str(winreg.QueryValueEx(key, "MachineGuid")[0])
        if system == "Linux":
            return Path("/etc/machine-id").read_text(encoding="utf-8").strip()
        if system == "Darwin":
            out = subprocess.run(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True,
                text=True,
                check=False,
            ).stdout
            for line in out.splitlines():
                if "IOPlatformUUID" in line:
                    return line.split('"')[-2]
    except Exception:  # noqa: BLE001 — fall through to the MAC-based fallback
        logger.warning("Could not read the OS machine id; using MAC fallback")
    return f"mac:{uuid.getnode()}"


def machine_code() -> str:
    """Short human-friendly code identifying this machine, e.g. ABCD-EFGH-IJKL-MNOP."""
    digest = hashlib.sha256(f"aip-machine:{_raw_machine_id()}".encode()).digest()
    b32 = base64.b32encode(digest).decode()
    return "-".join(b32[i : i + 4] for i in range(0, 16, 4))


def normalise(code: str) -> str:
    """Uppercase and strip separators/whitespace so codes survive retyping."""
    return "".join(ch for ch in code.upper() if ch.isalnum())


def verify_activation_code(code: str) -> bool:
    """True when *code* is a valid signature of THIS machine's code."""
    compact = normalise(code)
    message = f"aip-licence:{normalise(machine_code())}".encode()
    try:
        signature = base64.b32decode(compact + "=" * (-len(compact) % 8))
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(PUBLIC_KEY_HEX)).verify(
            signature, message
        )
    except (ValueError, InvalidSignature):
        return False
    return True


_activated: bool | None = None  # verified once per process; reset on activation


def is_activated() -> bool:
    global _activated
    if _activated is None:
        key = get_settings().licence_key
        _activated = bool(key) and verify_activation_code(key)
    return _activated


def reset_cache() -> None:
    global _activated
    _activated = None
