---
name: django-verification
description: Verification loop for Django projects — environment, lint, migrations, tests+coverage, security scan, and deploy readiness. Use before PRs / pre-deploy.
origin: ECC
---

# Django Verification Loop

Run before PRs, after major changes, and pre-deploy. Phases:

1. **Environment**: `python --version`, venv active, `pip list --outdated`, required env vars set.
2. **Code Quality**: `mypy .`, `ruff check . --fix`, `black . --check`, `isort . --check-only`, `python manage.py check --deploy`.
3. **Migrations**: `showmigrations`, `makemigrations --check`, `migrate --plan`; report pending/conflicts.
4. **Tests + Coverage**: `pytest --cov=apps --cov-report=term-missing --reuse-db`; report passed/failed and per-app coverage. Targets: Models 90 / Serializers 85 / Views 80 / Services 90 / Overall 80.
5. **Security**: `pip-audit`, `safety check`, `bandit -r .`, `python manage.py check --deploy`, `gitleaks detect`; report vulns/secrets/DEBUG.
6. **Django Commands**: `check`, `collectstatic --noinput`, superuser, DB integrity, cache reachable.
7. **Performance**: N+1 (Debug Toolbar / `debugsqlshell`), missing indexes, query count < 50/page.
8. **Static Assets**: `npm audit`, build, verify `staticfiles/`.
9. **Config Review**: `DEBUG=False`, `SECRET_KEY`>30, `ALLOWED_HOSTS` set, HTTPS/HSTS, non-sqlite prod DB.
10. **Logging**: test logger output, log file writable.
11. **API Docs (DRF)**: `generateschema` valid, Swagger accessible.
12. **Diff Review**: `git diff --stat`, grep `print(` / `pdb` / `DEBUG=True` / todo / fixme / hardcoded secrets.

## Output Template
```
DJANGO VERIFICATION REPORT
Phase 1 Environment: ✓ Python 3.11, venv active, env vars set
Phase 4 Tests: 247 passed, 0 failed; Overall 87%
Phase 5 Security: ✗ pip-audit: 2 vulns (fix required)
RECOMMENDATION: ⚠️ Fix pip-audit vulnerabilities before deploying
```

## Pre-Deploy Checklist
- [ ] All tests pass, coverage ≥80%
- [ ] No security vulns, no unapplied migrations
- [ ] DEBUG=False, SECRET_KEY/ALLOWED_HOSTS set, HTTPS/HSTS, static collected, logging, backups, cache/celery (if used)

## Quick Reference
| Check | Command |
| Type | `mypy .` |
| Lint | `ruff check .` |
| Migrations | `python manage.py makemigrations --check` |
| Tests | `pytest --cov=apps` |
| Security | `pip-audit && bandit -r .` |
| Deploy check | `python manage.py check --deploy` |
