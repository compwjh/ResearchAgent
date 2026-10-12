"""Claim value types shared by selection and CLI callers."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .documents import TaskDefinition
from .owners import OwnerIdentity


class ClaimError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__("{}: {}".format(code, detail))


@dataclass(frozen=True)
class Claim:
    task: TaskDefinition
    run_id: str
    attempt: int
    ide: str
    owner: OwnerIdentity
    claimed_at: str
    expires_at: str
    worktree_path: Path
    branch: str
    base_commit: str
    task_hash: str
    prompt_hash: str
    state: str
    recovery_of: Optional[str]
