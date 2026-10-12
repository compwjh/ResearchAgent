"""Local process identity checks used before attempting lease recovery."""

import hashlib
import os
import re
import secrets
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


class OwnerError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class OwnerStatus(str, Enum):
    ALIVE = "alive"
    DEAD = "dead"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class OwnerIdentity:
    executor_id: str
    host_id: str
    pid: int
    process_started_at: str
    token: str = field(repr=False)


def _host_id() -> str:
    if sys.platform.startswith("linux"):
        for name in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            try:
                value = Path(name).read_text(encoding="ascii").strip()
            except OSError:
                continue
            if re.fullmatch(r"[0-9a-fA-F]{32}", value):
                break
        else:
            raise OwnerError("owner_host_identity_unavailable")
        material = "linux:" + value.lower()
    elif sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["/usr/sbin/ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                env={"LC_ALL": "C"}, timeout=3, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            raise OwnerError("owner_host_identity_unavailable") from None
        match = re.search(r'"IOPlatformUUID"\s*=\s*"([0-9A-Fa-f-]+)"', result.stdout)
        if result.returncode != 0 or match is None:
            raise OwnerError("owner_host_identity_unavailable")
        material = "macos:" + match.group(1).lower()
    else:
        raise OwnerError("owner_platform_unsupported")
    return "sha256:" + hashlib.sha256(material.encode("ascii")).hexdigest()


def _linux_process_start(pid: int) -> Optional[str]:
    try:
        record = Path("/proc/{}/stat".format(pid)).read_text(encoding="ascii")
    except FileNotFoundError:
        return None
    split_at = record.rfind(")")
    if split_at < 0 or not record.startswith("{} (".format(pid)):
        raise OwnerError("owner_process_identity_unavailable")
    fields = record[split_at + 1:].split()
    if len(fields) <= 19:
        raise OwnerError("owner_process_identity_unavailable")
    if fields[0] in {"Z", "X"}:
        return None
    if not fields[19].isdigit():
        raise OwnerError("owner_process_identity_unavailable")
    boot = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", boot):
        raise OwnerError("owner_process_identity_unavailable")
    return "linux:{}:{}".format(boot.lower(), fields[19])


def _mac_process_start(pid: int) -> Optional[str]:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return None
    except PermissionError:
        raise OwnerError("owner_process_identity_unavailable") from None
    try:
        result = subprocess.run(
            ["/bin/ps", "-o", "state=", "-o", "lstart=", "-p", str(pid)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            env={"LC_ALL": "C"}, timeout=3, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        raise OwnerError("owner_process_identity_unavailable") from None
    parts = result.stdout.strip().split(None, 1)
    if result.returncode != 0 or len(parts) != 2:
        raise OwnerError("owner_process_identity_unavailable")
    if parts[0].startswith("Z"):
        return None
    try:
        started = datetime.strptime(parts[1], "%a %b %d %H:%M:%S %Y")
    except ValueError:
        raise OwnerError("owner_process_identity_unavailable") from None
    return "macos:" + started.strftime("%Y-%m-%dT%H:%M:%S")


def _process_start(pid: int) -> Optional[str]:
    if sys.platform.startswith("linux"):
        return _linux_process_start(pid)
    if sys.platform == "darwin":
        return _mac_process_start(pid)
    raise OwnerError("owner_platform_unsupported")


def current_owner(executor_id: str, *, pid: int) -> OwnerIdentity:
    """Capture an explicit, long-lived executor PID; never assume this CLI PID."""
    if not isinstance(executor_id, str) or not executor_id.strip() or type(pid) is not int or pid <= 0:
        raise OwnerError("owner_identity_invalid")
    host = _host_id()
    try:
        started = _process_start(pid)
    except (OSError, subprocess.SubprocessError):
        raise OwnerError("owner_process_identity_unavailable") from None
    if started is None:
        raise OwnerError("owner_process_not_alive")
    return OwnerIdentity(executor_id, host, pid, started, secrets.token_hex(32))


def observe_owner(owner: OwnerIdentity) -> OwnerStatus:
    """Return unknown unless this host can positively compare the exact process."""
    if (not isinstance(owner, OwnerIdentity) or type(owner.pid) is not int or owner.pid <= 0 or
            not owner.host_id or not owner.process_started_at):
        return OwnerStatus.UNKNOWN
    try:
        if owner.host_id != _host_id():
            return OwnerStatus.UNKNOWN
        started = _process_start(owner.pid)
    except (OwnerError, OSError, subprocess.SubprocessError):
        return OwnerStatus.UNKNOWN
    if started is None or started != owner.process_started_at:
        return OwnerStatus.DEAD
    return OwnerStatus.ALIVE
