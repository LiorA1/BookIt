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
- gunicorn (Docker setup only)
- WhiteNoise for static files

Direct dependencies are pinned in `requirements.txt`.

## Setup

Choose one of the two setups below. Both serve the API at
`http://127.0.0.1:8000/` and Django admin at `http://127.0.0.1:8000/admin/`;
stop one before starting the other, because both use port 8000.

### Local Setup (conda or venv)

Start PostgreSQL 16 in Docker:

```text
docker run --name bookit-db -e POSTGRES_PASSWORD=bookit -e POSTGRES_DB=bookit -p 5432:5432 -d postgres:16
```

Then, from PowerShell in the repository root, create a Python 3.12
environment with conda:

```powershell
conda create -n movement python=3.12
conda activate movement
```

or with venv:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
```

and continue in the activated environment:

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py seed_data
python manage.py runserver
```

### Docker Setup (docker compose)

`docker-compose.yml` runs the API under gunicorn together with its own
PostgreSQL 16 database:

```powershell
Copy-Item .env.docker.example .env.docker
docker compose up --build -d
docker compose exec api python manage.py seed_data
```

Both containers read `.env.docker`; the local `.env` is not used. The API
always connects to the compose `db` service (`DB_HOST=db`, `DB_PORT=5432`),
and the database container is initialized from the `POSTGRES_DB`,
`POSTGRES_USER`, and `POSTGRES_PASSWORD` values, which must match `DB_NAME`,
`DB_USER`, and `DB_PASSWORD` in the same file. Migrations and
`collectstatic` run automatically when the API container starts. The database
port is not published, so the stack does not clash with a `bookit-db`
container on port 5432, and its data persists in the `pgdata` volume.
`seed_data` requires `DEBUG=True`, the `.env.docker.example` default. Static
files (the Django admin assets) are served by WhiteNoise.

Follow the logs with `docker compose logs -f api`; stop the stack with
`docker compose down` (add `-v` to delete the database volume).

## Configuration

Each setup has its own environment file: the local setup reads `.env`
(template `.env.example`), and the Docker setup reads `.env.docker` (template
`.env.docker.example`). Both accept the variables below; `.env.docker` also
sets `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` for the database
container.

- `SECRET_KEY`: required Django secret; use a unique value outside development.
- `DEBUG`: accepts `1`, `true`, `yes`, or `on`; keep disabled in production.
- `ALLOWED_HOSTS`: comma-separated hostnames.
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`: required PostgreSQL database, user, and
  password. The `.env.example` values match the Docker command above.
- `DB_HOST`, `DB_PORT`: optional; default to `localhost` and `5432`.
- `SEED_PASSWORD`: optional shared password for seeded users.
- `BOOKING_MAX_ADVANCE_DAYS`: optional; how far ahead an appointment may be
  booked (default 365).

`.env` and `.env.docker` are ignored by Git.

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

The endpoint reference (requests, responses, status codes, query
parameters, correlation IDs, and error format) lives in [API.md](API.md).

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
|-- .env.docker.example # Docker environment template
|-- Dockerfile       # API image (gunicorn)
|-- docker-compose.yml # API and PostgreSQL stack
|-- requirements.txt # Pinned direct dependencies
|-- manage.py        # Django command entry point
|-- API.md           # Endpoint reference
|-- AGENTS.md        # Instructions for coding agents
|-- CONVENTIONS.md   # Engineering and API standards
`-- PLAN.md          # Product and implementation roadmap
```

## Running Tests

The tests use Django's test runner against PostgreSQL. Each run creates a
temporary `test_<DB_NAME>` database and drops it at the end, so the
development data is not touched, but `DB_USER` needs `CREATEDB` rights (the
default `postgres` user has them).

### Local Setup

With the environment active and the `bookit-db` container running:

```powershell
python manage.py test
```

Run a single app, test class, or test method by passing its dotted path:

```powershell
python manage.py test accounts
python manage.py test business.tests.BusinessListApiTests
python manage.py test business.tests.BusinessListApiTests.test_filter_by_category
```

Add `-v 2` to list each test as it runs.

### Docker Setup

With the stack running:

```powershell
docker compose exec api python manage.py test
```

The image contains a copy of the code from when it was built, so run
`docker compose up --build -d` after changing code or tests.

### Full Verification

Before handing off a change, also confirm that the project configuration is
valid and that no model change is missing a migration:

```powershell
python manage.py check
python manage.py makemigrations --check
python manage.py test
```

## Development Guidance

Read `CONVENTIONS.md` before changing code and `PLAN.md` before expanding
scope. Coding agents should also follow `AGENTS.md`.
