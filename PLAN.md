# BookIt Home Assignment Plan

## Scope and Priorities

This plan follows the assignment's required scope and its 4–6 hour time budget.
Required behavior and deliverables come before optional hardening or additional
product features. Business CRUD, service CRUD, availability generation,
notifications, deployment infrastructure, and other unrequested features are
out of scope.

Target stack:

- Python 3.12 (local development uses the conda environment `movement`)
- Django 5.2 LTS
- Django REST Framework
- PostgreSQL 16 through the Django ORM and `psycopg`

Milestone numbers match the `ms-N` commit message prefixes.

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

## Milestone 1: Authentication — Implemented

Implemented in `ms-1`. Remaining work is verification against the
requirements only; no new features.

1. Public `POST /api/auth/register/` and `POST /api/auth/login/`.
2. JWTs contain at least user ID and role.
3. Every other endpoint requires JWT authentication.
4. Unauthenticated requests return 401 and authenticated-but-forbidden
   requests return 403.

Acceptance criteria:

- Authentication requirements have focused API tests.
- The public role representation remains `Client` or `BusinessOwner`.

Verification outcome:

- `CustomUser.save()` normalizes email on every write path, and a
  `Lower(email)` unique constraint (`accounts` migration `0003`) enforces
  case-insensitive uniqueness in the database.
- The login 401 response carries `WWW-Authenticate: Bearer realm="api"`.
- Tests cover malformed, wrong-signature, and expired access tokens (401).
- Routes keep trailing slashes; the README and Postman collection use them.
- `/admin/` is a documented staff-only session-auth exception to the JWT rule.
- Deferred: the 403 path is tested with real role-gated endpoints in
  Milestones 4 and 5; token print removal stays in Milestone 7; the refresh
  endpoint stays optional bonus work.
- Re-run the authentication tests after Milestone 3 moves to Django 5.2 and
  PostgreSQL.

## Milestone 2: Business List — Implemented

Implemented in `ms-2`. Remaining work is verification against the
requirements only; no new features.

1. `GET /api/businesses/` pagination and total count.
2. Category filter.
3. Free-text name search.

Acceptance criteria:

- Business list requirements have focused API tests.

## Milestone 3: Required Runtime and Data Setup

1. Add `requirements.txt` with exact pins for direct dependencies: Django
   5.2 LTS, DRF, Simple JWT, `python-dotenv`, and `psycopg[binary]`.
2. Configure the default database for PostgreSQL from `DB_NAME`, `DB_USER`,
   `DB_PASSWORD`, `DB_HOST`, and `DB_PORT`. Values live in `.env`
   (`.env.example` holds the Docker values); no password default in code.
   Remove SQLite.
3. Use `CONN_MAX_AGE = 0` (one connection per request) with autocommit;
   atomic workflows use explicit `transaction.atomic()` in services.
4. Replace the Django 6.1-only `MAILERS` setting with the console
   `EMAIL_BACKEND` and point settings documentation links at Django 5.2.
5. Document and verify the required local database command:

```text
docker run --name bookit-db -e POSTGRES_PASSWORD=bookit -e POSTGRES_DB=bookit -p 5432:5432 -d postgres:16
```

6. Keep schema changes represented by Django migrations.
7. Add an idempotent `python manage.py seed_data` command in
   `business/management/commands/`:
   - 5 business owners with 4 businesses each (20 businesses), 10 clients,
     50 services, and 200 appointments;
   - an `admin@bookit.test` superuser with the `BusinessOwner` role;
   - all seeded users use the `@bookit.test` email domain and share one
     password;
   - deterministic data from hand-written name lists and a fixed random seed;
   - appointments on 30-minute business-hour slots within ±30 days of the
     run date, mixing past and future times and all statuses, with no
     duplicate service/start-time pairs;
   - each run, inside one transaction, deletes only `@bookit.test` users
     (cascading to their data) and recreates the full data set.
8. Update `README.md` setup: conda environment with Python 3.12,
   `requirements.txt`, the Docker PostgreSQL command, database environment
   variables, the seed command, and seeded login credentials.

Acceptance criteria:

- The Python 3.12 environment installs dependencies from `requirements.txt`
  and connects to the Docker PostgreSQL database.
- `migrate` and `seed_data` succeed repeatedly with the same resulting counts.
- Seeded credentials work.

## Milestone 4: Appointment Service and Endpoints

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

## Milestone 5: Owner-Only Business Summary

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

## Milestone 6: Required Middleware

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

## Milestone 7: Deliverables and Final Verification

1. Remove token debug output after notifying the user of that observable
   behavior change.
2. Finish `README.md` with:
   - Python 3.12 and Django 5 setup;
   - the exact PostgreSQL Docker command;
   - environment, migration, seed, test, and run commands;
   - seeded login credentials;
   - a 2–3 sentence explanation of per-request database connection and
     transaction scope and why it was chosen.
3. Add a Postman collection covering every required endpoint and authentication
   flow.
4. Run:

```powershell
python manage.py check
python manage.py makemigrations --check
python manage.py test
```

5. Review endpoint status codes, query efficiency, secrets, and logs.
6. Prepare logical changes for a meaningful commit history, but do not create,
   amend, or push any commit without explicit user permission.

## Optional Bonus — Only After Required Work

- Add a refresh-token endpoint if the existing token pair is retained.
- Add pytest unit tests for one service class.
- Add `docker-compose.yml` for the API and PostgreSQL.
- Add dedicated serializer validators where they improve clarity.
- Add login rate limiting.

Do not start bonus work while any required endpoint, middleware, seed data,
README content, Postman request, or required test remains incomplete.
