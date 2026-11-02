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
- Python 3.12, Django 5.2 LTS, and PostgreSQL 16 through `psycopg`, with
  pinned direct dependencies in `requirements.txt`.
- Idempotent, deterministic `seed_data` command.
- Appointment booking (`POST`) and role-scoped listing (`GET`) with a database
  exclusion constraint against overlapping bookings.
- Owner-only `GET /api/businesses/{id}/summary/` with database aggregation.

Must be corrected or completed:

- The two required custom middleware classes are missing.
- Token values are currently printed and must not appear in output or logs.
- The README lacks the required connection/transaction explanation.
- The Postman collection (`postman/BookIt.postman_collection.json`) covers
  auth, businesses, the business summary, and appointments.

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
  Known, accepted deviation from the assignment text, which writes the paths
  without a slash: a slashless `GET` is redirected (301), a slashless `POST`
  fails.
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

## Milestone 3: Required Runtime and Data Setup — Implemented

Implemented in `ms-3`.

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

Implementation decisions:

- Pins: Django 5.2.18, DRF 3.18.3, Simple JWT 5.5.1, `psycopg[binary]`
  3.3.6, `python-dotenv` 1.2.4.
- The migrations generated by Django 6.1.2 are kept unchanged; they apply
  cleanly on 5.2 and PostgreSQL.
- `DB_NAME`, `DB_USER`, and `DB_PASSWORD` are required; `DB_HOST` and
  `DB_PORT` default to `localhost` and `5432`. The app and the Django test
  runner's temporary database both use the `postgres` user.
- Seeded users share `SEED_PASSWORD`, falling back to the documented
  `BookIt-Demo-2026!`. The admin is a sixth `BusinessOwner` user with no
  businesses.
- Each owner has 2 Barbers and 2 Tutors businesses; businesses alternate
  between 3 and 2 services from fixed per-category name and price lists. All
  services last 30 minutes.
- Appointments fall on 30-minute slots from 09:00 to 18:00 Asia/Jerusalem,
  every day, stored in UTC. No service and no client is double-booked. Past
  appointments are Confirmed or Cancelled; future ones are Pending, Confirmed,
  or Cancelled.
- The command refuses to run unless `DEBUG=True` (it deletes data and creates
  a superuser with a documented password). Only the guard is covered by an
  automated test; the data set was verified by running the command twice.
- A database constraint against double booking is deferred to Milestone 4.
- The connection/transaction README explanation stays in Milestone 7.

## Milestone 4: Appointment Service and Endpoints — Implemented

Implemented in `ms-4`.

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
9. Decide booking-conflict rules and their database constraint (for example,
   unique service and start time), deferred from Milestone 3.

Acceptance criteria:

- Role, authentication, ownership, filters, response schema, and transaction
  behavior are tested.
- Owners cannot see appointments for another owner's businesses.

Implementation decisions:

- Booking conflict rule: the active (non-`Cancelled`) appointments of one
  service may not overlap in time. It is enforced by the PostgreSQL exclusion
  constraint `appointment_service_no_overlap` over the half-open range
  `[start_time, end_time)`, so back-to-back bookings are allowed and a
  cancelled appointment frees its time. A conflict returns `409` with a
  `start_time` field error; the service maps the constraint's
  `IntegrityError` to `SlotUnavailableError`. There is no slot grid: any
  future start time is valid as long as it does not overlap.
- The constraint needs no extension. Equality on the service is expressed as
  overlap of one-point ranges, `int8range(service_id, service_id, '[]') &&`
  (`BigIntPointRange` in `business/db_functions.py`), which GiST supports
  natively; the alternative is `BtreeGistExtension` with `service_id WITH =`.
  Other options (slot grid with a unique constraint, trigger with an advisory
  lock, lock-and-check in the service) were evaluated and rejected: they
  either need a product rule, custom PL/pgSQL, or do not bind every writer.
- Overlap is checked against stored `end_time` snapshots, so editing a
  service's duration later does not make old and new bookings conflict
  unpredictably; it also means a duration edit never re-checks old bookings.
- `Appointment.end_time` is a stored `NOT NULL` snapshot of
  `start_time + service.duration_minutes`, with
  `CHECK (end_time > start_time)`. `AppointmentService` sets it; `save()` fills
  it only when empty (admin, shell). `bulk_create` and `QuerySet.update()`
  skip `save()`, so `seed_data` sets it explicitly. Later edits to a service's
  duration or an appointment's `start_time` do not recompute it.
- Migration `0003` adds the column nullable, backfills it with SQL, then
  enforces `NOT NULL` and adds both constraints. It fails if existing data
  already contains overlapping active appointments for a service.
- `POST` body is `{"service": <id>, "start_time": <ISO 8601 with offset>}`.
  Only users whose current database role is `Client` may book (`403`
  otherwise, including owners booking their own business); the JWT role claim
  is not trusted. New appointments are always `Pending`. An unknown service,
  a naive/invalid datetime, a start time that is not in the future, or a start
  time more than `BOOKING_MAX_ADVANCE_DAYS` (default 365) ahead returns `400`
  on `service` or `start_time`. The horizon is checked before any date
  arithmetic, so values near year 9999 no longer overflow into a `500`.
- `GET` accepts `from`/`to` (timezone-aware, inclusive, on `start_time`;
  `from > to` returns `400` on `to`) and a repeatable `status` name filter.
  Choice values in query strings (`status`, and `category` on the business
  list) are lowercase only (`pending`, `barbers`); other casing returns `400`.
  Responses use the same spelling (`"status": "pending"`,
  `"category": "barbers"`), produced by `public_name()` in
  `business/serializers.py`. The `role` field of the accounts API keeps its
  `Client`/`BusinessOwner` spelling.
  Results are ordered by `start_time, id` and paginated with
  `StandardPageNumberPagination`. Cancelled appointments are included unless
  filtered out.
- Responses nest `service`, `business`, and `client` display fields and render
  the status by lowercase name. Datetimes are rendered in UTC.
- `AppointmentStatus` moved from a nested class to a module-level enum so the
  model's `Meta` constraints can reference it.
- The business list and appointment list queries select only the columns their
  response serializers render (`.only()`), so owner and client password hashes
  and emails are not fetched; tests assert that the query count stays flat. The
  `.only()` column lists must be kept in sync with the response serializers.
- Django admin: the appointment form uses autocomplete lookups for `service`
  and `client`, and `ServiceAdmin` joins `business`, so the form no longer runs
  one query per service.
- Not included: retrieve-by-id, cancel, and confirm endpoints.
- A service with `duration_minutes = 0` would violate the `end_time` check and
  surface as a server error; a `Service` duration constraint was not added.

## Milestone 5: Owner-Only Business Summary — Implemented

Implemented in `ms-5`.

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

Implementation decisions:

- Response is the standard paginated envelope (`StandardPageNumberPagination`)
  over the business's services, ordered by service `id`. Each item is
  `{service_id, name, appointment_count, expected_revenue}`; there is no
  top-level business object. `expected_revenue` is a decimal string
  (`"150.00"`); a service with no matching appointments reports `0` and
  `"0.00"`.
- "Future" means `start_time > now` (an appointment starting exactly now, or
  already in progress, is not counted). Pending and Confirmed count; Cancelled
  never does. `BusinessSummaryService` takes an injectable clock.
- Check order: unauthenticated `401`; `IsBusinessOwner` checks the current
  database role first, so any `Client` gets `403` whatever the id; an unknown
  business id returns `404`; a business owned by someone else raises
  `BusinessNotOwnedError`, mapped to `403` by the view. There is no superuser
  bypass: the seeded `admin@bookit.test` owns no business and gets `403`.
- Counts and revenue come from one grouped `Service` query:
  `Count("appointments", filter=...)` and `count * F("price")` in an
  `ExpressionWrapper` with a `DecimalField` output. The query selects only
  `id`, `name`, and `price`, and the view loads the business with
  `.only("id", "owner")`. A request runs a fixed number of queries (business
  lookup, pagination count, page rows) regardless of services or appointments;
  a test asserts it.
- The `.only()` columns must stay in sync with
  `BusinessSummaryItemResponseSerializer`.

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

## Backlog (post-assignment)

Not scheduled; revisit when the trigger appears.

- **Database connection scaling.** `CONN_MAX_AGE = 0` opens a PostgreSQL
  connection per request. This is deliberate for the assignment because it
  keeps the per-request connection and transaction scope simple. Revisit when
  sustained load or `max_connections` pressure appears. Options:
  - Django 5.1+ native pooling (`OPTIONS={"pool": True}` with
    `psycopg[pool]`); it is mutually exclusive with `CONN_MAX_AGE > 0`.
  - PgBouncer in transaction mode.
  - `CONN_MAX_AGE` with `CONN_HEALTH_CHECKS`.

  Keep the README connection/transaction explanation in sync with the chosen
  option.

## Optional Bonus — Only After Required Work

- Add a refresh-token endpoint if the existing token pair is retained.
- Add pytest unit tests for one service class.
- Add `docker-compose.yml` for the API and PostgreSQL.
- Add dedicated serializer validators where they improve clarity.
- Add login rate limiting.

Do not start bonus work while any required endpoint, middleware, seed data,
README content, Postman request, or required test remains incomplete.
