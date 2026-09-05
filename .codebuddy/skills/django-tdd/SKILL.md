---
name: django-tdd
description: Django TDD with pytest-django, factory_boy, mocking, coverage, and DRF API testing. Use when writing Django tests.
origin: ECC
---

# Django Testing with TDD

Test-driven development for Django applications using pytest, factory_boy, and DRF.

## Setup
- `pytest.ini`: `DJANGO_SETTINGS_MODULE=config.settings.test`, `addopts = --reuse-db --nomigrations --cov=apps`.
- test settings: sqlite `:memory:`, `MIGRATION_MODULES=DisableMigrations`, fast password hashers, `EMAIL_BACKEND=locmem`, `CELERY_TASK_ALWAYS_EAGER=True`.
- `tests/conftest.py` fixtures: `user`, `admin_user`, `authenticated_client`, `api_client`, `authenticated_api_client`.

## Factory Boy
- `DjangoModelFactory` with `Meta.model`; `SubFactory`, `PostGenerationMethodCall('set_password', ...)`, `FuzzyDecimal`, `create_batch(n)`.

## Model Tests
- `@pytest.mark.django_db`; create via factory; assert fields, managers, validation (`full_clean()` raises `ValidationError`), constraints.

## View / API Tests
- `client` (Django test client) for templates; `APIClient` for DRF; `force_authenticate(user)`.
- Test list / retrieve / create-unauthorized / create-authorized / update / delete / filter / search.
- Serializer tests: `is_valid()`, `save()`, field validation errors.

## Mocking
- `@patch('apps.payments.services.stripe')` for external calls.
- Email: `mail.outbox` with `override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')`.

## Integration
- Full flow: register → login → browse → add to cart → checkout, with `patch` on payment gateway.

## Coverage
- `pytest --cov=apps --cov-report=html`; targets: Models 90%, Serializers 85%, Views 80%, Services 90%, Overall 80%.

## Best Practices
- DO: factories, one assertion per test, descriptive names, test permissions, fast (`--reuse-db --nomigrations`).
- DON'T: test Django internals/third-party, ignore failures, make tests dependent, over-mock, use prod DB.

## Quick Reference
| `pytest.mark.django_db` | Enable DB access |
| `client` / `api_client` | Test clients |
| `factory.create_batch(n)` | Create N objects |
| `force_authenticate()` | Bypass auth in tests |
| `patch('mod.fn')` | Mock dependency |
