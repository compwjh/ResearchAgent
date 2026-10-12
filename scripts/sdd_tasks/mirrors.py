"""Validate Task status mirrors without changing repository files."""
import json
import os
import re
from pathlib import Path, PurePosixPath
from typing import Dict

from .atomic import read_text
from .documents import META, PROMPT, TaskDefinition, _pairs

LABELS = {"pending": "待执行", "blocked": "阻塞", "completed": "完成", "cancelled": "取消"}
MARKER = "当前状态："

class MirrorError(ValueError):
    def __init__(self, path: str, detail: str) -> None:
        self.code, self.path = "TASK_MIRROR_INVALID", Path(path)
        super().__init__("{} {}: {}".format(self.code, path, detail))

def _bad(path: str, detail: str) -> None:
    raise MirrorError(path, detail)

def _file(root: Path, path: Path, label: str) -> Path:
    _no_symlink(root, path, label)
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError):
        _bad(label, "missing file or path escapes repository root")
    if not resolved.is_file():
        _bad(label, "expected a file")
    return resolved


def _no_symlink(root: Path, path: Path, label: str) -> None:
    try:
        path.relative_to(root)
    except ValueError:
        _bad(label, "path escapes repository root")
    current = path
    while current != root:
        if current.is_symlink():
            _bad(label, "canonical mirror path contains a symlink")
        current = current.parent

def _read(path: Path, label: str) -> str:
    try:
        return read_text(path)
    except (OSError, UnicodeError, ValueError) as exc:
        _bad(label, "cannot read UTF-8 file: " + str(exc))

def _paths(task: TaskDefinition, repo_root: Path):
    try:
        root = Path(repo_root).resolve(strict=True)
        sid, task_id = task.metadata["spec_id"], task.metadata["task_id"]
        if not re.fullmatch(r"\d{3}", sid) or not re.fullmatch(r"spec-" + sid + r"-task-\d{2}", task_id):
            _bad("task.path", "invalid task/spec id")
        supplied = Path(task.path)
        if ".." in supplied.parts:
            _bad("task.path", "source path must not contain parent traversal")
        lexical = Path(os.path.abspath(supplied if supplied.is_absolute() else root / supplied))
        source_rel = lexical.relative_to(root)
        source = _file(root, lexical, source_rel.as_posix())
    except (OSError, ValueError, KeyError) as exc:
        if isinstance(exc, MirrorError):
            raise
        _bad("task.path", "source path is not contained in repository root")
    number = task_id[-2:]
    if (source_rel.parent != Path("docs/sdd/plans") / sid or
            not re.fullmatch(r"task-" + number + r"-.+\.md", source_rel.name)):
        _bad(source_rel.as_posix(), "Task source path does not match its spec/task id")
    spec_matches = sorted((root / "docs/sdd/specs").glob(sid + "-*.md"))
    if len(spec_matches) != 1:
        _bad("docs/sdd/specs/" + sid, "expected exactly one spec document")
    spec_lex = spec_matches[0]
    spec_rel = spec_lex.relative_to(root)
    spec = _file(root, spec_lex, spec_rel.as_posix())
    readme_lex = root / "docs/sdd/plans" / sid / "README.md"
    readme_rel = readme_lex.relative_to(root)
    readme = _file(root, readme_lex, readme_rel.as_posix())
    return root, source_rel, source, spec_rel, spec, readme_rel, readme

def _blocks(text: str, path: str):
    lines = text.splitlines(keepends=True)
    plain = [line.rstrip("\r\n") for line in lines]
    found = [[i for i, line in enumerate(plain) if line == marker] for marker in META + PROMPT]
    if any(len(indices) != 1 for indices in found):
        _bad(path, "metadata and prompt markers must each occur exactly once")
    mb, me, pb, pe = (indices[0] for indices in found)
    if mb >= me or pb >= pe or not (me < pb or pe < mb):
        _bad(path, "metadata and prompt markers overlap")
    raw = "".join(lines[mb + 1:me])
    try:
        metadata = json.loads(raw, object_pairs_hook=_pairs)
    except ValueError as exc:
        _bad(path, "invalid metadata JSON: " + str(exc))
    if not isinstance(metadata, dict):
        _bad(path, "metadata must be an object")
    return lines, mb, me, raw, metadata, "".join(lines[pb + 1:pe])

def _task_status(text: str, expected: str, path: str):
    lines = text.splitlines(keepends=True)
    hits = [(i, line) for i, line in enumerate(lines) if MARKER in line]
    boundary = next((i for i, line in enumerate(lines) if line.startswith("## ")), len(lines))
    if len(hits) != 1 or hits[0][0] >= boundary or hits[0][1].count(MARKER) != 1:
        _bad(path, "expected one top-level human status line")
    index, line = hits[0]
    body = line.rstrip("\r\n")
    match = re.search(r"当前状态：(`?)([^`]+)(`?)$", body)
    if not match or bool(match.group(1)) != bool(match.group(3)) or match.group(2).strip() != expected:
        _bad(path, "human status does not match metadata.status")
    return lines, index, match

def _link(root: Path, ref_rel: Path, cell: str, source: Path, label: str) -> None:
    links = re.findall(r"\[[^\]]+\]\(([^)\s]+)\)", cell)
    if len(links) != 1 or links[0].startswith(("/", "\\")) or "\\" in links[0] or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", links[0]):
        _bad(label, "expected one relative Markdown Task link")
    target = PurePosixPath(links[0])
    current = root / ref_rel.parent
    try:
        for part in target.parts:
            current = current.parent if part == ".." else current if part == "." else current / part
            current.relative_to(root)
            if current.is_symlink():
                _bad(label, "Markdown link path contains a symlink")
        resolved = current.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError):
        _bad(label, "Markdown link is missing or escapes repository root")
    if resolved != source:
        _bad(label, "Markdown link does not target the Task source")

def _row(text: str, number: str, status: str, root: Path, ref_rel: Path,
         source: Path, label: str):
    lines = text.splitlines(keepends=True)
    hits = []
    for index, line in enumerate(lines):
        if not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.rstrip("\r\n").strip().strip("|").split("|")]
        if cells and cells[0] == number:
            hits.append((index, line, cells))
    if len(hits) != 1:
        _bad(label, "expected exactly one Task table row")
    index, line, cells = hits[0]
    pipes = [i for i, char in enumerate(line) if char == "|"]
    if len(cells) != 5 or len(pipes) != 6:
        _bad(label, "Task table row must have five cells")
    _link(root, ref_rel, cells[2], source, label)
    if cells[4] != status:
        _bad(label, "table status does not match metadata.status")
    return lines, index, pipes[-2] + 1, pipes[-1]

def _inspect(task: TaskDefinition, repo_root: Path):
    root, task_rel, source, spec_rel, spec, readme_rel, readme = _paths(task, repo_root)
    label = task_rel.as_posix()
    task_text, spec_text, readme_text = _read(source, label), _read(spec, spec_rel.as_posix()), _read(readme, readme_rel.as_posix())
    status = task.metadata.get("status")
    if status not in LABELS:
        _bad(label, "invalid metadata.status")
    task_status = _task_status(task_text, LABELS[status], label)
    task_parts = _blocks(task_text, label)
    actual_meta, actual_prompt = task_parts[4], task_parts[5]
    if actual_meta != task.metadata or actual_prompt != task.prompt:
        _bad(label, "Task source differs from TaskDefinition")
    number = task.metadata["task_id"][-2:]
    spec_row = _row(spec_text, number, LABELS[status], root, spec_rel, source, spec_rel.as_posix())
    readme_row = _row(readme_text, number, LABELS[status], root, readme_rel, source, readme_rel.as_posix())
    return (root, task_rel, spec_rel, readme_rel, task_text, spec_text, readme_text,
            task_parts, task_status, spec_row, readme_row)

def validate_mirrors(task: TaskDefinition, repo_root: Path) -> None:
    _inspect(task, repo_root)


def _status_span(raw: str):
    decoder = json.JSONDecoder()
    index = len(raw) - len(raw.lstrip())
    if index == len(raw) or raw[index] != "{":
        _bad("metadata", "expected a JSON object")
    index += 1
    while True:
        while index < len(raw) and raw[index].isspace():
            index += 1
        if index == len(raw):
            _bad("metadata", "unterminated JSON object")
        if raw[index] == "}":
            break
        key, index = decoder.raw_decode(raw, index)
        while index < len(raw) and raw[index].isspace():
            index += 1
        if index == len(raw) or raw[index] != ":":
            _bad("metadata", "expected a JSON field separator")
        index += 1
        while index < len(raw) and raw[index].isspace():
            index += 1
        start = index
        _, index = decoder.raw_decode(raw, index)
        if key == "status":
            return start, index
        while index < len(raw) and raw[index].isspace():
            index += 1
        if index < len(raw) and raw[index] == ",":
            index += 1
        elif index == len(raw) or raw[index] != "}":
            _bad("metadata", "expected a JSON field delimiter")
    _bad("metadata", "status field is missing")


def _replace_row(parts, status: str) -> str:
    lines, index, start, end = parts
    line = lines[index]
    body, ending = line.rstrip("\r\n"), line[len(line.rstrip("\r\n")):]
    cell = body[start:end]
    leading, trailing = cell[:len(cell) - len(cell.lstrip())], cell[len(cell.rstrip()):]
    lines[index] = body[:start] + leading + status + trailing + body[end:] + ending
    return "".join(lines)


def render_status_update(task: TaskDefinition, status: str, repo_root: Path) -> Dict[str, str]:
    if status not in LABELS:
        _bad("metadata.status", "unsupported status")
    (root, task_rel, spec_rel, readme_rel, task_text, spec_text, readme_text,
     task_parts, task_status, spec_row, readme_row) = _inspect(task, repo_root)
    lines, mb, me, raw = task_parts[:4]
    start, end = _status_span(raw)
    new_raw = raw[:start] + json.dumps(status) + raw[end:]
    _, index, match = task_status
    line = lines[index]
    body, ending = line.rstrip("\r\n"), line[len(line.rstrip("\r\n")):]
    lines[index] = body[:match.start(2)] + LABELS[status] + body[match.end(2):] + ending
    return {
        task_rel.as_posix(): "".join(lines[:mb + 1]) + new_raw + "".join(lines[me:]),
        spec_rel.as_posix(): _replace_row(spec_row, LABELS[status]),
        readme_rel.as_posix(): _replace_row(readme_row, LABELS[status]),
    }
