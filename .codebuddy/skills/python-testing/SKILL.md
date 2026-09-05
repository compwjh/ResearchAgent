---
name: python-testing
description: Python testing strategies with pytest, TDD methodology, fixtures, mocking, parametrization, async tests, and coverage. Use when writing or reviewing Python tests (FastAPI/Flask/backend).
origin: ECC
---

# Python Testing Patterns

Comprehensive testing strategies for Python applications using pytest, TDD, and best practices.

## When to Activate
- Writing new Python code (follow TDD: red → green → refactor)
- Designing test suites for Python projects
- Reviewing Python test coverage
- Setting up testing infrastructure (pytest)

## Core Philosophy
- **TDD cycle**: RED (failing test) → GREEN (minimal impl) → REFACTOR.
- **Coverage**: target 80%+; 100% on critical paths. Measure with `pytest --cov`.

## pytest Fundamentals
- Basic: `def test_x(): assert ...`
- Assertions: equality/inequality/truthiness/membership/`is`/`isinstance`/comparisons.
- Exceptions: `with pytest.raises(ValueError, match="invalid input") as exc: ...` then `assert str(exc.value) == "..."`.

## Fixtures
- Basic: `@pytest.fixture def sample(): return {...}`; consumed as a test argument.
- Setup/teardown via `yield`: code before `yield` runs before, after runs as teardown.
- Scopes: `function` (default), `module`, `session`.
- `autouse=True` runs before every test automatically.
- Shared fixtures belong in `tests/conftest.py`.
- Parametrized fixture: `@pytest.fixture(params=[1,2,3])`.

## Parametrization
- `@pytest.mark.parametrize("a,b,expected", [(2,3,5),(0,0,0)])`.
- Custom IDs via `ids=[...]` for readable output.
- Markers defined in `pytest.ini`; run `pytest -m "not slow"`, `-m integration`.

## Mocking & Patching
- `from unittest.mock import patch, Mock`.
- `@patch("pkg.external_call") def test(m): m.return_value={"ok":True}; m.assert_called_once()`.
- Raise: `m.side_effect = ConnectionError(...)`.
- Async: `@pytest.mark.asyncio` + `pytest-asyncio`; mock with `return_value={...}` and assert `assert_awaited_once()`.
- Use `autospec=True` to catch API misuse.

## Async Testing
- `@pytest.mark.asyncio async def test(): result = await fn()`.
- Async fixtures: `async def client(): async with app.test_client() as c: yield c`.

## Test Organization
- `tests/conftest.py`, `tests/unit/`, `tests/integration/`, `tests/e2e/`.
- Group with classes: `class TestX: def test_y(self): ...`.
- Naming: `test_user_login_with_invalid_credentials_fails`.

## Testing API Endpoints (FastAPI/Flask)
```python
@pytest.fixture
def client():
    app = create_app(testing=True)
    return app.test_client()

def test_get_user(client):
    r = client.get("/api/users/1")
    assert r.status_code == 200
    assert r.json["id"] == 1
```

## Testing Database Operations
- Use `tmp_path` or in-memory DB; fixtures with `yield` for teardown.
- SQLite `:memory:` for unit-level DB tests.

## pytest Config
```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = --strict-markers --cov=<pkg> --cov-report=term-missing
markers =
    slow: marks tests as slow
    integration: marks tests as integration
```

## Running
```bash
pytest                        # all
pytest tests/test_utils.py    # file
pytest tests/test_utils.py::test_fn
pytest -v                     # verbose
pytest -m "not slow"          # skip slow
pytest -x --maxfail=3         # stop on failures
pytest --lf                   # last failed
pytest -k "user"              # keyword
pytest --cov=<pkg> --cov-report=html
```

## Best Practices
- DO: TDD, one behavior per test, descriptive names, fixtures, mock externals, test edge cases, 80%+ coverage, keep fast.
- DON'T: test implementation internals, complex conditionals in tests, ignore failures, test third-party code, share state, catch exceptions (use `raises`), `print`, brittle mocks.

## Quick Reference
| Pattern | Usage |
| `pytest.raises()` | Expected exceptions |
| `@pytest.fixture` | Reusable fixtures |
| `@pytest.mark.parametrize` | Multiple inputs |
| `@patch()` | Mock functions/classes |
| `tmp_path` | Temp directory |
| `pytest --cov` | Coverage report |
