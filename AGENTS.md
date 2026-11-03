# BookIt Agent Guide

## Purpose

BookIt is a Django REST Framework API for discovering service businesses and
booking appointments. Preserve the existing app boundaries and API behavior
when making changes.

## Repository Map

- `BookIt/`: project settings, root URLs, ASGI, and WSGI.
- `accounts/`: email-based custom users, roles, registration, login, and JWTs.
- `business/`: businesses, services, appointments, discovery, and pagination.
- `<app>/migrations/`: generated database history; never edit applied
  migrations to change current behavior.
- `CONVENTIONS.md`: detailed coding and API conventions.
- `PLAN.md`: current capabilities, known gaps, and implementation roadmap.

## Architecture Rules

- Keep domain code inside its Django app; project-level configuration belongs
  in `BookIt/`.
- Use models for persistence and constraints, serializers for transport
  validation and representation, services for multi-step business operations,
  and views for HTTP orchestration.
- Define domain-specific exceptions in each app's `exceptions.py`; do not
  declare them in service, view, serializer, or model modules.
- Keep views thin. Inject service classes through class attributes when a view
  needs a replaceable dependency.
- Use `get_user_model()` or `settings.AUTH_USER_MODEL`; never import
  `CustomUser` into domain code.
- Store choice values as integers and expose their symbolic names or labels at
  the API boundary.
- Optimize relationship access with `select_related()`/`prefetch_related()` and
  explicitly order every paginated queryset.
- Try to avoid inefficient queries where possible, raise a flag where you encounter them.

## API Rules

- All endpoints are authenticated by default through the global DRF settings.
  Public endpoints must explicitly set both `authentication_classes = []` and
  `permission_classes = [AllowAny]`.
- Name transport serializers by purpose: `*RequestSerializer`,
  `*QuerySerializer`, and `*ResponseSerializer`.
- Validate query parameters with a serializer rather than reading and parsing
  raw strings in a view.
- Return DRF status constants and stable, field-oriented validation errors.
- Do not leak passwords, token internals, secrets, or stack traces.
- Preserve the existing `/api/auth/` and `/api/businesses/` URL prefixes unless
  a versioned migration is planned.

## Data and Security Rules

- Create migrations for every model change and commit them with the code.
- Use transactions for operations that must succeed atomically and database
  constraints as the final defense against races.
- Keep secrets in environment variables. Never commit `.env`, databases,
  credentials, or generated local state.
- Normalize email through the custom user manager and keep duplicate-email
  handling case-insensitive.
- Enforce ownership and role authorization server-side; a JWT role claim is
  context, not proof that current database permissions still allow an action.

## Testing and Verification

- Add focused service tests for domain behavior and API tests for status,
  schema, permissions, validation, filtering, and pagination.
- Reproduce race-sensitive rules with database constraints, not tests alone.
- Before handing off a change, run:

```powershell
python manage.py check
python manage.py makemigrations --check
python manage.py test
```

- If dependencies are unavailable, report that explicitly rather than claiming
  tests passed.

## Change Discipline

- Read the relevant model, serializer, service, view, URL, migration, and tests
  before changing a feature.
- Never create, amend, or push a commit without the user's explicit permission.
- Notify the user before making a behavioral change. Behavioral changes include
  altered API contracts, status codes, permissions, validation, persistence,
  side effects, or externally observable runtime behavior.
- Prefer the smallest complete change; avoid unrelated cleanup.
- Do not rewrite existing migrations or silently change public response shapes.
- Update `README.md`, `API.md`, `CONVENTIONS.md`, or `PLAN.md` when setup,
  architecture, public APIs, or roadmap status changes.
