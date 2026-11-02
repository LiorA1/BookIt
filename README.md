# BookIt

BookIt is a Django REST Framework API for service-business discovery and
appointment booking. It provides email-based accounts with JWT authentication,
paginated business search, appointment booking and role-scoped listing, an
owner-only business summary, and request logging with correlation IDs and
generic JSON error responses.

## Features

- Custom user model with `Client` and `BusinessOwner` roles.
- Public registration and login.
- JWT access and refresh tokens.
- Authenticated business listing.
- Category filtering and case-insensitive name search.
- Appointment booking for clients and role-scoped, filterable appointment lists.
- Owner-only per-service business summary (future appointment count and expected revenue).
- Configurable page-number pagination.
- Django admin support for users, businesses, services, and appointments.
- Service-level and API-level tests.

Businesses and services are created and edited through Django admin (or
`seed_data`); the API has no create, update, or delete endpoints for them.

## Technology

- Python 3.12 and Django 5.2 LTS
- Django REST Framework
- Django REST Framework Simple JWT
- python-dotenv
- PostgreSQL 16 through the `psycopg` driver

Direct dependencies are pinned in `requirements.txt`.

## Setup

Start PostgreSQL 16 in Docker:

```text
docker run --name bookit-db -e POSTGRES_PASSWORD=bookit -e POSTGRES_DB=bookit -p 5432:5432 -d postgres:16
```

Then, from PowerShell in the repository root:

```powershell
conda create -n movement python=3.12
conda activate movement
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py seed_data
python manage.py runserver
```

The development server starts at `http://127.0.0.1:8000/`; Django admin is at
`http://127.0.0.1:8000/admin/`.

## Configuration

Copy `.env.example` to `.env` and set:

- `SECRET_KEY`: required Django secret; use a unique value outside development.
- `DEBUG`: accepts `1`, `true`, `yes`, or `on`; keep disabled in production.
- `ALLOWED_HOSTS`: comma-separated hostnames.
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`: required PostgreSQL database, user, and
  password. The `.env.example` values match the Docker command above.
- `DB_HOST`, `DB_PORT`: optional; default to `localhost` and `5432`.
- `SEED_PASSWORD`: optional shared password for seeded users.
- `BOOKING_MAX_ADVANCE_DAYS`: optional; how far ahead an appointment may be
  booked (default 365).

`.env` is ignored by Git.

## Database Connections and Transactions

Database connections are opened lazily on the first query and, with
`CONN_MAX_AGE = 0`, closed at the end of each request; requests that do not
access the database open no connection. Django uses autocommit for ordinary ORM
statements, while write workflows that must succeed or fail together use
explicit `transaction.atomic()` blocks in the service layer, with PostgreSQL
constraints providing race safety. This choice favors simplicity, explicit
transaction boundaries, short transactions, low idle-connection usage, and low
stale-connection risk.

## Seed Data

`python manage.py seed_data` creates a deterministic demo data set: 5 business
owners with 4 businesses each (20 businesses, 10 Barbers and 10 Tutors), 10
clients, 50 services, and 200 appointments. Appointments use 30-minute slots
from 09:00 to 18:00 Asia/Jerusalem time, within 30 days before or after the run
date, with no double-booked service or client.

The command only runs with `DEBUG=True` (the `.env.example` default) and
exits with an error otherwise, because it deletes data and creates a superuser
with a documented password.

Each run deletes every user whose email ends in `@bookit.test` (matched
case-insensitively), together with their businesses, services, and
appointments, and recreates the data set in a single transaction. Because
deleting a service also deletes its appointments, bookings that other users
made on seeded services are removed too. Users with any other email domain,
and everything else they own, are untouched. Rerunning always produces the
same counts.

Seeded logins all share the password `BookIt-Demo-2026!` unless `SEED_PASSWORD`
is set:

| Role | Emails |
| --- | --- |
| Business owner | `owner1@bookit.test` to `owner5@bookit.test` |
| Client | `client1@bookit.test` to `client10@bookit.test` |
| Admin (superuser, `BusinessOwner` role, no businesses) | `admin@bookit.test` |

## API

All request and response bodies use JSON. API routes use trailing slashes
(for example `/api/auth/register/`).

Known limitation (accepted): the assignment text writes the paths without a
trailing slash (for example `/api/appointments`). Django's `APPEND_SLASH`
answers a slashless `GET` with a `301` redirect to the slashed route, but a
slashless `POST` is not usable: it raises an error when `DEBUG` is on and is
redirected without its body otherwise. Always call the routes with the
trailing slash.

A ready-to-import Postman collection with collection-scoped variables lives in
`postman/`; see [Postman](#postman).

Every `/api/` route except register and login requires a JWT access token.
Django admin at `/admin/` is a deliberate exception: it is a staff-only
operational tool that uses Django session login and is not part of the public
API.

### Register

`POST /api/auth/register/` is public.

```json
{
  "email": "owner@example.com",
  "password": "S3cure-pass!",
  "full_name": "Yossi Cohen",
  "role": "BusinessOwner"
}
```

Valid roles are `Client` and `BusinessOwner`. A successful request returns
`201 Created` with `id`, `email`, `full_name`, and `role`. Emails are stored
lowercased and are unique case-insensitively. A missing or invalid field, a
weak password, or an already registered email returns `400 Bad Request` with
the error under that field (for example `email`).

### Login

`POST /api/auth/login/` is public.

```json
{
  "email": "owner@example.com",
  "password": "S3cure-pass!"
}
```

A successful request returns `access` and `refresh` JWT strings; the access
token carries `user_id` and `role` claims. A missing or invalid `email` or
`password` field returns `400 Bad Request`; wrong credentials return
`401 Unauthorized` with a `WWW-Authenticate: Bearer realm="api"` header. Send
the access token to protected routes:

```text
Authorization: Bearer <access-token>
```

### List Businesses

`GET /api/businesses/` requires authentication and returns a paginated
`count`, `next`, `previous`, and `results` envelope.

Supported query parameters:

- `page`: page number.
- `page_size`: requested size; defaults to 20 and is capped at 100.
- `category`: `barbers` or `tutors` (lowercase only; other casing returns
  `400`). Responses render the category the same way (`"category": "barbers"`).
- `search`: case-insensitive business-name search; multiple terms must all
  match.

Example:

```text
GET /api/businesses/?category=barbers&search=fade&page_size=10
```

### Book an Appointment

`POST /api/appointments/` requires authentication and a user whose current
role is `Client`; business owners receive `403 Forbidden`.

```json
{
  "service": 1,
  "start_time": "2026-11-10T10:00:00Z"
}
```

`start_time` must include a UTC offset (`Z` or `+02:00`), be in the future, and
be at most `BOOKING_MAX_ADVANCE_DAYS` (default 365) days ahead.
The appointment starts as `pending`, and `end_time` is `start_time` plus the
service duration. Responses use `201 Created`. Errors are field-oriented and
return `400 Bad Request`: on `service` for an unknown service, and on
`start_time` for an invalid, naive, past, or too-distant time, or when the
booking would overlap an active appointment of the same service
(`"This time slot is already booked."`). Back-to-back bookings are allowed, and
cancelled appointments free their time.

### List Appointments

`GET /api/appointments/` requires authentication and returns the same
paginated envelope as the business list. Clients see their own appointments;
business owners see appointments for services in businesses they own.
Results are ordered by `start_time`.

Supported query parameters:

- `page`, `page_size`: as for businesses.
- `from`, `to`: inclusive bounds on `start_time`, timezone-aware ISO 8601.
- `status`: `pending`, `confirmed`, or `cancelled` (lowercase only); repeat the
  parameter to match several (`?status=pending&status=confirmed`).

Each item contains `id`, `status`, `start_time`, `end_time`, and nested
`service`, `business`, and `client` objects. `status` and the business
`category` are rendered in lowercase (`"status": "pending"`), matching the
query values.

### Business Summary

`GET /api/businesses/<id>/summary/` is owner-only and returns the same
paginated envelope, with one item per service of the business, ordered by
service id (`page`, `page_size` as for businesses):

```json
{
  "service_id": 7,
  "name": "Fade cut",
  "appointment_count": 3,
  "expected_revenue": "150.00"
}
```

`appointment_count` counts the service's future (`start_time` after now),
non-cancelled appointments, and `expected_revenue` is that count multiplied by
the service price, as a decimal string; both are computed in the database. A
service without such appointments reports `0` and `"0.00"`.

`401` without a token. `403` for a user whose current role is `Client`
(whatever the id) and for a business owner who does not own the business (there
is no superuser bypass). `404` for an unknown business id.

### Correlation ID and Errors

Every response, including errors, carries an `X-Correlation-ID` header with a
UUID4 generated by the server for that request. A client-supplied
`X-Correlation-ID` header is ignored. The same ID appears in the server logs.

The server writes one JSON object per line to the console, for example:

```json
{"timestamp": "2026-11-02T20:44:25.402000+00:00", "level": "INFO", "logger": "bookit.request", "message": "request completed", "correlation_id": "023b8b34-9550-4fc4-bf4c-b9df235b089d", "method": "GET", "path": "/api/businesses/", "status": 200, "duration_ms": 12.4}
```

Request lines are INFO for 1xx-3xx, WARNING for 4xx, and ERROR for 5xx; the
query string is not logged. An unexpected server error is logged in full
(with its traceback) on the `bookit.exception` logger and answered with `500`
and the generic body `{"detail": "Internal server error."}`. Errors raised
outside a view, for example in other middleware, get the same JSON response
through Django's `handler500` and are logged by Django's own `django.request`
logger in plain text. With `DEBUG=True`, Django's debug page is shown instead.

## Postman

Import `postman/BookIt.postman_collection.json` into Postman. It covers
register, login, the business list (pagination, `category`, `search`), the
owner-only business summary, and the appointment list and booking endpoints,
including the 400, 401, 403 and 404
cases, and uses the seeded logins (`client1@bookit.test`, `owner1@bookit.test`,
password `BookIt-Demo-2026!`) through collection variables. Start the server
first and run the folders in order: the login requests save the tokens, and
"List my appointments (client)" saves a real `serviceId` for the booking
requests, because database ids change on every `seed_data` run. Change
`baseUrl` if the server is not on `http://127.0.0.1:8000`. The summary requests
use the `businessId` and `otherBusinessId` saved by "List businesses
(paginated)".

The collection can also run headless: `npx newman run
postman/BookIt.postman_collection.json`. Registering and booking requests
write real rows to the development database.

## Domain Model

- A user has one role and authenticates by normalized email.
- A business belongs to an owner and has a category.
- A service belongs to a business and defines duration and price.
- An appointment links a client to a service at a start time, stores its end
  time, and has `Pending`, `Confirmed`, or `Cancelled` status. The
  non-cancelled appointments of a service cannot overlap in time; PostgreSQL
  enforces this with an exclusion constraint.

## Project Layout

```text
BookIt/
|-- BookIt/          # Project settings, root URLs, middleware, logging, and the JSON 500 view
|-- accounts/        # Users, registration, login, and JWT services
|-- business/        # Businesses, services, appointments, and discovery
|-- .env.example     # Local environment template
|-- requirements.txt # Pinned direct dependencies
|-- manage.py        # Django command entry point
|-- AGENTS.md        # Instructions for coding agents
|-- CONVENTIONS.md   # Engineering and API standards
`-- PLAN.md          # Product and implementation roadmap
```

## Verification

With the conda environment active and PostgreSQL running (tests create and
drop a temporary `test_<DB_NAME>` database, so `DB_USER` needs `CREATEDB`
rights):

```powershell
python manage.py check
python manage.py makemigrations --check
python manage.py test
```

## Development Guidance

Read `CONVENTIONS.md` before changing code and `PLAN.md` before expanding
scope. Coding agents should also follow `AGENTS.md`.
