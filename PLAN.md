# BookIt Home Assignment Plan

## Scope and Priorities

This plan follows the assignment's required scope and its 4–6 hour time budget.
Required behavior and deliverables come before optional hardening or additional
product features. Business CRUD, service CRUD, availability generation,
notifications, deployment infrastructure, and other unrequested features are
out of scope.

Target stack:

- Python 3.12
- Django 5
- Django REST Framework
- PostgreSQL 16 through the Django ORM and `psycopg`

## Current State

Already implemented:

- Custom email-based user model with `Client` and `BusinessOwner` roles.
- Registration and login endpoints.
- JWT access and refresh token generation with user ID and role claims.
- `Business`, `Service`, and `Appointment` models and Django admin support.
- Authenticated, paginated business listing with category and name filters.
- Total matching business count in the paginated response.
- Explicit business response serialization and optimized owner loading.
- Service and API tests for authentication and business listing.

Must be corrected or completed:

- The project was generated with Django 6.1.2 and uses SQLite; the assignment
  requires Python 3.12, Django 5, PostgreSQL 16, and the `psycopg` driver.
- No dependency manifest is committed.
- No repeatable seed command exists.
- Appointment POST/list endpoints and role-based ownership queries are missing.
- The owner-only business summary endpoint and ORM aggregation are missing.
- The two required custom middleware classes are missing.
- Token values are currently printed and must not appear in output or logs.
- The README lacks PostgreSQL setup, seeded credentials, and the required
  connection/transaction explanation.
- No Postman collection exists.

## Phase 1: Required Runtime and Data Setup

1. Pin a Python 3.12-compatible Django 5 release, DRF, Simple JWT,
   `python-dotenv`, and `psycopg`.
2. Configure the default database from environment variables for PostgreSQL.
3. Document and verify the required local database command:

```text
docker run --name bookit-db -e POSTGRES_PASSWORD=bookit -e POSTGRES_DB=bookit -p 5432:5432 -d postgres:16
```

4. Keep schema changes represented by Django migrations.
5. Add an idempotent management command that seeds approximately 20 businesses,
   50 services, 200 appointments, and several users.
6. Put stable seeded login credentials in the README.
7. Remove token debug output after notifying the user of that observable
   behavior change.

Acceptance criteria:

- A clean Python 3.12 environment can install dependencies and connect to the
  Docker PostgreSQL database.
- `migrate` and the seed command succeed repeatedly.
- The seeded counts are approximately those requested and credentials work.

## Phase 2: Authentication and Business List Verification

1. Preserve public `POST /api/auth/register/` and `POST /api/auth/login/`.
2. Verify JWTs contain at least user ID and role.
3. Verify every other endpoint requires JWT authentication.
4. Verify unauthenticated requests return 401 and authenticated-but-forbidden
   requests return 403.
5. Preserve `GET /api/businesses/` pagination, total count, category filter,
   and free-text name search.

Acceptance criteria:

- Authentication and business requirements have focused API tests.
- The public role representation remains `Client` or `BusinessOwner`.

## Phase 3: Appointment Service and Endpoints

1. Add `AppointmentService` with ORM/repository dependencies passed explicitly.
2. Add `POST /api/appointments/`; only a `Client` may book a service.
3. Run appointment writes inside `transaction.atomic()`.
4. Add `GET /api/appointments/` with optional `from`, `to`, and `status`
   filters.
5. Scope the list from current database ownership:
   - clients see appointments where they are the client;
   - business owners see appointments for services belonging to businesses
     they own.
6. Add dedicated request/query/response serializers.
7. Include useful service and business display fields.
8. Use `select_related()` to prevent N+1 queries.

Acceptance criteria:

- Role, authentication, ownership, filters, response schema, and transaction
  behavior are tested.
- Owners cannot see appointments for another owner's businesses.

## Phase 4: Owner-Only Business Summary

1. Add `GET /api/businesses/{id}/summary/`.
2. Return 403 to an authenticated caller who does not own the business.
3. Return one item per service with:
   - count of future, non-cancelled appointments;
   - expected revenue computed as appointment count multiplied by service
     price.
4. Compute counts and revenue in the database with filtered Django ORM
   aggregation and expressions; do not loop over appointments in Python.

Acceptance criteria:

- Tests cover the owner, another owner, a client, anonymous access, cancelled
  appointments, past appointments, and services with zero appointments.
- Query count does not grow with the number of services or appointments.

## Phase 5: Required Middleware

1. Add global exception middleware that:
   - catches otherwise unhandled exceptions;
   - logs the full exception server-side;
   - returns a generic JSON/Problem Details-style 500 response;
   - never exposes stack traces or internal details.
2. Add request logging middleware that:
   - accepts or creates a correlation ID;
   - logs method, path, response status, and duration;
   - attaches the correlation ID to the response headers.
3. Register both custom middleware classes in a deliberate order.

Acceptance criteria:

- Focused tests verify the generic 500 body, server-side logging, timing log
  fields, and correlation response header.

## Phase 6: Deliverables and Final Verification

1. Finish `README.md` with:
   - Python 3.12 and Django 5 setup;
   - the exact PostgreSQL Docker command;
   - environment, migration, seed, test, and run commands;
   - seeded login credentials;
   - a 2–3 sentence explanation of per-request database connection and
     transaction scope and why it was chosen.
2. Add a Postman collection covering every required endpoint and authentication
   flow.
3. Run:

```powershell
python manage.py check
python manage.py makemigrations --check
python manage.py test
```

4. Review endpoint status codes, query efficiency, secrets, and logs.
5. Prepare logical changes for a meaningful commit history, but do not create,
   amend, or push any commit without explicit user permission.

## Optional Bonus — Only After Required Work

- Add a refresh-token endpoint if the existing token pair is retained.
- Add pytest unit tests for one service class.
- Add `docker-compose.yml` for the API and PostgreSQL.
- Add dedicated serializer validators where they improve clarity.
- Add login rate limiting.

Do not start bonus work while any required endpoint, middleware, seed data,
README content, Postman request, or required test remains incomplete.
