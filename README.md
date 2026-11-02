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
- Configurable page-number pagination.
- Django admin support for users, businesses, services, and appointments.
- Service-level and API-level tests.

Services and appointments are currently available as models and through Django
admin; their public API workflows are planned in `PLAN.md`.

## Technology

- Python and Django 6.1.2
- Django REST Framework
- Django REST Framework Simple JWT
- python-dotenv
- SQLite for local development

The repository does not yet include a dependency manifest. The setup command
below reflects packages imported by the current source.

## Setup

From PowerShell in the repository root:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install "Django==6.1.2" djangorestframework djangorestframework-simplejwt python-dotenv
Copy-Item .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Use a Python version supported by Django 6.1. If PowerShell blocks virtual
environment activation, set an appropriate execution policy for your user or
invoke `.venv\Scripts\python.exe` directly.

The development server starts at `http://127.0.0.1:8000/`; Django admin is at
`http://127.0.0.1:8000/admin/`.

## Configuration

Copy `.env.example` to `.env` and set:

- `SECRET_KEY`: required Django secret; use a unique value outside development.
- `DEBUG`: accepts `1`, `true`, `yes`, or `on`; keep disabled in production.
- `ALLOWED_HOSTS`: comma-separated hostnames.

`.env` and local SQLite databases are ignored by Git.

## API

All request and response bodies use JSON. API routes use trailing slashes
(for example `/api/auth/register/`); requests without the trailing slash are
not redirected and fail.

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
- `category`: `Barbers` or `Tutors`.
- `search`: case-insensitive business-name search; multiple terms must all
  match.

Example:

```text
GET /api/businesses/?category=Barbers&search=fade&page_size=10
```

## Domain Model

- A user has one role and authenticates by normalized email.
- A business belongs to an owner and has a category.
- A service belongs to a business and defines duration and price.
- An appointment links a client to a service at a start time and has
  `Pending`, `Confirmed`, or `Cancelled` status.

## Project Layout

```text
BookIt/
|-- BookIt/          # Project settings and root URL configuration
|-- accounts/        # Users, registration, login, and JWT services
|-- business/        # Businesses, services, appointments, and discovery
|-- .env.example     # Local environment template
|-- manage.py        # Django command entry point
|-- AGENTS.md        # Instructions for coding agents
|-- CONVENTIONS.md   # Engineering and API standards
`-- PLAN.md          # Product and implementation roadmap
```

## Verification

With the virtual environment active:

```powershell
python manage.py check
python manage.py makemigrations --check
python manage.py test
```

## Development Guidance

Read `CONVENTIONS.md` before changing code and `PLAN.md` before expanding
scope. Coding agents should also follow `AGENTS.md`.
