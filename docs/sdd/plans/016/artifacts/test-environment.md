# Spec016 test environment preflight

Date: 2026-10-11 UTC

## Environment paths

- Business/test environment: `/workspace/researchagent-venv311` — CPython 3.11.16.
- CLI-only environment: `/workspace/researchagent-cli-venv39` — CPython 3.9.25.
- uv-managed interpreters: `/workspace/.uv/python/cpython-3.11-linux-x86_64-gnu/bin/python3.11` and `/workspace/.uv/python/cpython-3.9-linux-x86_64-gnu/bin/python3.9`.
- uv cache: `/tmp/spec016-uv-cache`.

## Installed versions

| Environment | Python | pytest | pytest-cov | Ruff |
| --- | --- | --- | --- | --- |
| Business | 3.11.16 | 9.1.1 | 7.1.0 | 0.16.10 |
| CLI-only | 3.9.25 | 8.4.2 | not installed | 0.16.10 |

Business installed `/workspace/ResearchAgent/requirements.txt`, `requirements-dev.txt`, plus pytest and pytest-cov for test collection and the repository's coverage workflow. CLI installed pytest and Ruff only as direct tools; their runtime dependencies are present transitively. Ruff is pinned within the repository's `>=0.16.6,<0.17` range in both environments. No pytest-asyncio references were found in the repository, so it was not installed.

The requirements install includes the Playwright Python package (`1.52.0`); Playwright browser binaries were not downloaded.

## Commands and outcomes

| Command/check | Exit | Result |
| --- | ---: | --- |
| `uv python install 3.11 3.9` using the default cache | 2 | Blocked because `/home/agent/.cache/uv` is read-only. |
| `UV_CACHE_DIR=/tmp/spec016-uv-cache UV_PYTHON_INSTALL_DIR=/workspace/.uv/python uv python install 3.11 3.9` | 0 | Installed CPython 3.11.16 and 3.9.25. uv warned it could not create optional links under read-only `/home/agent/.local/bin`; both interpreters work from their explicit paths. |
| `uv venv --python <3.11 interpreter> /workspace/researchagent-venv311` | 0 | Created business environment. |
| `uv venv --python <3.9 interpreter> /workspace/researchagent-cli-venv39` | 0 | Created CLI environment. |
| `uv pip install --python /workspace/researchagent-venv311/bin/python -r /workspace/ResearchAgent/requirements.txt -r /workspace/ResearchAgent/requirements-dev.txt` | 0 | Resolved and installed 87 packages, including Ruff 0.16.10. |
| `uv pip install --python /workspace/researchagent-cli-venv39/bin/python pytest ruff` | 0 | Installed pytest 8.4.2 and Ruff; Ruff was subsequently pinned to the project's compatible range. |
| `uv pip install --python /workspace/researchagent-cli-venv39/bin/python 'ruff>=0.16.6,<0.17'` | 0 | Replaced Ruff 0.17.0 with 0.16.10. |
| `uv pip install --python /workspace/researchagent-venv311/bin/python pytest pytest-cov` | 0 | Installed pytest 9.1.1 and pytest-cov 7.1.0 for business test collection/coverage workflows. |
| `PYTHONDONTWRITEBYTECODE=1 .../python -c 'import backend.app.main; ...'` from `/workspace/ResearchAgent` | 0 | `backend.app.main import ok`. |
| Python / pytest / Ruff version commands in both environments | 0 | Versions shown above. |
| `uv pip check --python /workspace/researchagent-venv311/bin/python` | 0 | 93 packages checked; all compatible. |
| `uv pip check --python /workspace/researchagent-cli-venv39/bin/python` | 0 | 9 packages checked; all compatible. |
| `PYTHONDONTWRITEBYTECODE=1 .../python -m pytest --collect-only -q -o addopts= -o cache_dir=/tmp/spec016-preflight/pytest-cache tests` | 0 | 2,896 tests collected in 28.62 seconds; no test cases were executed. Full output: `/tmp/spec016-preflight/pytest-collection.log`. |

## Warnings and failed diagnostics

- The business requirements install emitted `httpx==0.28.1` warning that the `s` extra is not defined. Installation succeeded; the `socks` extra and other dependencies resolved. No dependency conflicts were reported by `uv pip check`.
- uv emitted a hardlink warning because the cache and virtualenv are on different filesystems; it fell back to copying files successfully.
- `python -m pip show ruff pytest` in the CLI environment exited 1 because uv-created environments do not include pip. Package versions were verified with `uv pip list` and executable version commands instead; no pip package was added.
- No tracked requirements or source files were changed as part of environment preparation. Network installs used the inherited proxy/CA configuration; neither was overridden.
