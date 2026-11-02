# BookIt

BookIt is a Django REST Framework API for service-business discovery and
appointment booking. The current implementation provides email-based accounts,
JWT authentication, core booking-domain models, and paginated business search.

## Features

- Custom user model with `Client` and `BusinessOwner` roles.
- Public registration and login.
- JWT access and refresh tokens.
- Authenticated business listing.
- Category filtering and case-insensitive name search.
- Appointment booking for clients and role-scoped, filterable appointment lists.
- Configurable page-number pagination.
- Django admin support for users, businesses, services, and appointments.
- Service-level and API-level tests.

Services are currently available as models and through Django admin;
appointments are also available through the booking and listing API.

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

A ready-to-import Postman collection and environment live in `postman/`; see
[Postman](#postman).

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
lowercased and are unique case-insensitively.

### Login

`POST /api/auth/login/` is public.

```json
{
  "email": "owner@example.com",
  "password": "S3cure-pass!"
}
```

A successful request returns `access` and `refresh` JWT strings; the access
token carries `user_id` and `role` claims. Invalid credentials return
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
service duration. Responses use `201 Created`. Errors are field-oriented:
`400` for an unknown service or an invalid, naive, past, or too-distant
`start_time`, and
`409 Conflict` on `start_time` when the booking would overlap an active
appointment of the same service. Back-to-back bookings are allowed, and
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

## Postman

Import `postman/BookIt.postman_collection.json` into Postman. It covers
register, login, the business list (pagination, `category`, `search`) and the
appointment list and booking endpoints, including the 400, 401, 403 and 409
cases, and uses the seeded logins (`client1@bookit.test`, `owner1@bookit.test`,
password `BookIt-Demo-2026!`) through collection variables. Start the server
first and run the folders in order: the login requests save the tokens, and
"List my appointments (client)" saves a real `serviceId` for the booking
requests, because database ids change on every `seed_data` run. Change
`baseUrl` if the server is not on `http://127.0.0.1:8000`.

The collection can also run headless: `npx newman run
postman/BookIt.postman_collection.json`. Registering and booking requests
write real rows to the development database.

The business summary endpoint is not implemented yet, so it is not in the
collection.

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
|-- BookIt/          # Project settings and root URL configuration
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
