"""Strictly read the current status from a canonical SDD Spec document."""

import re
from pathlib import Path

from .atomic import contained, read_text

STATES = {"待确认", "已确认", "实施中", "已完成", "阻塞"}
CLAIMABLE_STATES = {"已确认", "实施中"}
_STATUS_LINE = re.compile(
    r"^\*\*当前状态：(?:`(?P<code>待确认|已确认|实施中|已完成|阻塞)`|"
    r"(?P<plain>待确认|已确认|实施中|已完成|阻塞))"
    r"(?:（[^（）\r\n]+）|\([^()\r\n]+\))?\*\*$"
)
_HEADING = re.compile(r"^#{1,6}[ \t]+.+[ \t]*$")
_STATUS_HEADING = re.compile(r"^##[ \t]+状态[ \t]*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


class SpecStatusError(ValueError):
    """A missing, ambiguous, unsafe, or malformed Spec status source."""

    def __init__(self, path: Path, detail: str) -> None:
        self.code = "SPEC_STATUS_INVALID"
        self.path = Path(path)
        super().__init__("{} {}: {}".format(self.code, self.path.as_posix(), detail))


def _display_path(path: Path) -> Path:
    path = Path(path)
    if not path.is_absolute():
        return path
    parts = path.parts
    for index in range(len(parts) - 2):
        if parts[index:index + 3] == ("docs", "sdd", "specs"):
            return Path(*parts[index:])
    return Path(path.name)


def _visible_lines(lines: list) -> list:
    visible, fence = [], None
    for line in lines:
        match = _FENCE.match(line)
        if fence is None and match:
            fence = (match.group(1)[0], len(match.group(1)))
            visible.append(None)
        elif fence is not None:
            closing = re.match(r"^ {0,3}(`{3,}|~{3,})[ \t]*$", line)
            if closing and closing.group(1)[0] == fence[0] and len(closing.group(1)) >= fence[1]:
                fence = None
            visible.append(None)
        else:
            visible.append(line)
    return visible


def _parse(text: str, path: Path) -> str:
    lines = _visible_lines(text.splitlines())
    sections = [i for i, line in enumerate(lines)
                if line is not None and _STATUS_HEADING.fullmatch(line)]
    if len(sections) != 1:
        raise SpecStatusError(path, "expected exactly one '## 状态' section")
    start = sections[0] + 1
    end = next((i for i in range(start, len(lines))
                if lines[i] is not None and _HEADING.fullmatch(lines[i])), len(lines))
    current = [line.strip() for line in lines[start:end]
               if line is not None and line.strip().startswith("**当前状态")]
    if len(current) != 1:
        raise SpecStatusError(path, "expected exactly one current status line")
    match = _STATUS_LINE.fullmatch(current[0])
    if match is None:
        raise SpecStatusError(path, "current status line has invalid syntax or state")
    return match.group("code") or match.group("plain")


def read_spec_status(spec_path: Path) -> str:
    """Read one Spec status line without following any symlink component."""
    path = Path(spec_path)
    display = _display_path(path)
    try:
        return _parse(read_text(path), display)
    except SpecStatusError:
        raise
    except (OSError, UnicodeError, ValueError) as exc:
        raise SpecStatusError(display, "cannot safely read Spec") from exc


def load_spec_status(task, repo_root: Path) -> str:
    """Resolve and read the unique Spec in the Task's registered canonical worktree."""
    from .catalog import CatalogError, discover_worktrees

    spec_id = getattr(task, "metadata", {}).get("spec_id")
    fallback = Path("docs/sdd/specs/unknown")
    try:
        main = Path(repo_root).resolve()
        if not isinstance(spec_id, str) or not re.fullmatch(r"\d{3}", spec_id):
            raise ValueError("invalid spec_id")
        fallback = Path("docs/sdd/specs") / (spec_id + "-*.md")
        worktree_path = task.metadata["worktree"]["path"]
        roots = discover_worktrees(main)
        if not roots or roots[0] != main:
            raise ValueError("invalid main worktree")
        authority = contained(main, worktree_path).resolve()
        if authority not in roots:
            raise ValueError("canonical worktree is not registered")
        if not authority.is_dir():
            raise ValueError("canonical worktree is missing")
        directory = contained(authority, "docs/sdd/specs")
        if not directory.is_dir():
            raise ValueError("canonical Spec directory is missing")
        candidates = sorted(directory.glob(spec_id + "-*.md"))
        if len(candidates) != 1:
            raise ValueError("expected exactly one canonical Spec, found {}".format(len(candidates)))
        source = candidates[0]
        relative = source.relative_to(main).as_posix()
        contained(authority, source.relative_to(authority).as_posix())
    except CatalogError as exc:
        raise SpecStatusError(fallback, "cannot discover registered canonical worktree") from exc
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise SpecStatusError(fallback, "canonical Spec or worktree is invalid") from exc
    return _read_with_path(source, Path(relative))


def _read_with_path(source: Path, relative: Path) -> str:
    try:
        return _parse(read_text(source), relative)
    except SpecStatusError:
        raise
    except (OSError, UnicodeError, ValueError) as exc:
        raise SpecStatusError(relative, "cannot safely read Spec") from exc


def is_claimable(state: str) -> bool:
    return state in CLAIMABLE_STATES
