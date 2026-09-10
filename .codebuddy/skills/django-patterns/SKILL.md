---
name: django-patterns
description: Django architecture patterns, REST API design with DRF, ORM best practices, caching, signals, middleware, and service layer. Use when building or reviewing Django applications.
origin: ECC
---

# Django Development Patterns

Production-grade Django architecture patterns for scalable, maintainable applications.

## When to Activate
- Building Django web applications / DRF APIs
- Django ORM, models, migrations
- Caching, signals, middleware

## Project Structure
- `config/settings/{base,development,production,test}.py` (split settings)
- `apps/<app>/{models,views,serializers,urls,permissions,filters,services,tests}/`

## Split Settings
- base: `SECRET_KEY` from env, `DEBUG=False`, `INSTALLED_APPS`, `MIDDLEWARE`, `DATABASES`.
- production: `SECURE_SSL_REDIRECT`, `SESSION_CSRF_COOKIE_SECURE`, HSTS, file logging.

## Model Design
- Custom user via `AbstractUser`; `Meta`: `db_table`, `ordering`, `indexes`, `CheckConstraint`.
- QuerySet/Manager: `objects = CustomQuerySet.as_manager()`; chainable `active()`, `select_related`, `prefetch_related`.
- Slug generation in `save()`.

## DRF Patterns
- Serializers: `ModelSerializer`, `read_only_fields`, `SerializerMethodField`, `validate_<field>`, cross-field `validate()`.
- ViewSets: `queryset` with `select_related`/`prefetch_related`, `permission_classes`, `filter_backends`, `filterset_class`, `search_fields`, `ordering_fields`; `get_serializer_class()` per action; `perform_create` injects `request.user`; custom `@action`.

## Service Layer
- `@transaction.atomic` for writes; keep business logic out of views; views stay thin.

## Caching
- `cache_page` per view; low-level `cache.get/set`; template fragment `{% cache %}`.

## Signals
- `post_save` receivers in `signals.py`; import in `apps.py ready()`.

## Middleware
- `MiddlewareMixin`; `process_request` / `process_response`.

## Performance
- Avoid N+1: `select_related` (FK), `prefetch_related` (M2M).
- Indexes on hot fields; `bulk_create` / `bulk_update` / `bulk_delete`.

## Quick Reference
| Pattern | Use |
| Split settings | dev/prod/test |
| Custom QuerySet | Reusable queries |
| Service layer | Business logic |
| ViewSet | REST endpoints |
| `select_related` | FK optimization |
| `prefetch_related` | M2M optimization |
| Signals | Event-driven |
