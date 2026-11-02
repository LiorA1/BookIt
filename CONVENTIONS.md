# BookIt Conventions

This document records conventions already present in the codebase and the
standards to follow as the API grows.

## Python and Django

- Use Python with four-space indentation and PEP 8 naming.
- Use double quotes for new Python strings for consistency with most current
  modules.
- Order imports as standard library, third-party packages, then local modules,
  with one blank line between groups.
- Give public classes and non-obvious domain logic concise docstrings.
- Prefer explicit names over abbreviations and keep functions focused.
- Use Django configuration rather than hard-coded environment-specific values.

## Project Structure

Each domain is a Django app:

- `models.py`: persisted entities, choices, indexes, and constraints.
- `serializers.py`: request/query validation and response representation.
- `services.py`: reusable business workflows.
- `exceptions.py`: domain-specific exception classes.
- `views.py`: HTTP coordination only.
- `urls.py`: app-local routes with stable names for `reverse()`.
- `admin.py`: operational access to models.
- `tests.py`: service and API behavior.

Add a dedicated module only when one of these files becomes difficult to
navigate. Avoid circular imports between apps.

## Naming

- Models and services use singular PascalCase names: `Business`, `UserService`.
- Views end in `View`; custom exceptions end in `Error`.
- Serializers state their direction or purpose:
  `RegisterRequestSerializer`, `BusinessListQuerySerializer`,
  `UserResponseSerializer`.
- URL names use lowercase kebab case, such as `business-list`.
- Reverse relations use descriptive plural names, such as `businesses`,
  `services`, and `appointments`.
- Tests describe observable behavior, such as
  `test_invalid_category_returns_400`.

## Models and Migrations

- Reference users with `settings.AUTH_USER_MODEL` in models and
  `get_user_model()` elsewhere.
- Use `models.IntegerChoices` for compact persisted enums.
- Use `gettext_lazy()` for user-facing model field labels.
- Add `related_name` to relationships.
- Put integrity rules in database constraints whenever possible.
- Add indexes only for demonstrated query patterns; keep index names explicit.
- Generate migrations with `python manage.py makemigrations`. Never edit an
  applied migration to represent a new schema change.
- Include model changes and their migrations in the same commit.

## Services and Transactions

- Put multi-step writes, authentication workflows, and race handling in service
  classes.
- Accept dependencies in constructors when doing so makes behavior testable.
- Use keyword-only parameters for service operations with several arguments.
- Wrap atomic workflows in `transaction.atomic()`.
- Translate expected persistence failures into domain exceptions, then map
  those exceptions to HTTP responses in the view.
- Keep every custom domain exception in the app's `exceptions.py`.
- Do not print credentials, tokens, or other request data. Use structured
  logging for operational diagnostics when logging is configured.

## Serializers and API Responses

- Validate all external input with DRF serializers, including query strings.
- Convert public choice names to internal enum values during validation.
- Render enum names or labels, never unexplained integer values. Choice
  values such as `status` and `category` use the lowercase member name in
  query strings and responses alike (`public_name()` in
  `business/serializers.py`).
- Mark response-only fields read-only and password fields write-only.
- Keep response shapes stable and explicit through response serializers.
- Return validation errors under the relevant field when possible.

## Views, URLs, and Permissions

- Rely on the global authenticated permission by default.
- Public views explicitly use `AllowAny` and disable authentication.
- Keep views responsible for serializer invocation, service calls, and response
  status only.
- Use DRF status constants rather than numeric literals.
- Mount app URLs below `/api/` in `BookIt/urls.py`.
- Keep trailing slashes consistent with the existing routes. This deviates
  from the assignment's slashless paths and is accepted; a slashless `POST`
  is not supported.
- Apply role and ownership checks before reads or writes to protected objects.

## Queries, Filtering, and Pagination

- Avoid N+1 queries with `select_related()` and `prefetch_related()`.
- Apply deterministic ordering before pagination.
- Use `StandardPageNumberPagination` for standard list endpoints: default 20,
  client-selectable through `page_size`, maximum 100.
- Validate custom filters in a query serializer.
- Preserve filter parameters in pagination links.

## Tests

- Use Django `TestCase` for services and DRF `APITestCase` for endpoints.
- Name test classes after the unit or endpoint under test.
- Test successful behavior, validation failures, authentication, authorization,
  response shape, and persistence side effects.
- Add regression tests before fixing a reported defect when practical.
- Use factories or helpers when repeated setup becomes noisy; keep test data
  readable.
- Run `python manage.py check`, `python manage.py makemigrations --check`, and
  `python manage.py test` before handoff.

## Configuration and Documentation

- Store local values in `.env`, using `.env.example` as the committed template.
- Never commit secret keys, tokens, local databases, or virtual environments.
- Add and pin a dependency in the project manifest when introducing a package.
- Update `README.md` for setup or public API changes.
- Update `PLAN.md` when a milestone is completed or reprioritized.
- Notify the user before making any externally observable behavioral change.
- Never create, amend, or push Git commits without explicit user permission.
