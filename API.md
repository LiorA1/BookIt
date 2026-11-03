# BookIt API

All request and response bodies use JSON. API routes use trailing slashes
(for example `/api/auth/register/`).

Known limitation (accepted): the assignment text writes the paths without a
trailing slash (for example `/api/appointments`). Django's `APPEND_SLASH`
answers a slashless `GET` with a `301` redirect to the slashed route, but a
slashless `POST` is not usable: it raises an error when `DEBUG` is on and is
redirected without its body otherwise. Always call the routes with the
trailing slash.

A ready-to-import Postman collection with collection-scoped variables lives in
`postman/`; see [Postman](README.md#postman).

Every `/api/` route except register and login requires a JWT access token.
Django admin at `/admin/` is a deliberate exception: it is a staff-only
operational tool that uses Django session login and is not part of the public
API.

## Register

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

## Login

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

## List Businesses

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

## Book an Appointment

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

## List Appointments

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

## Business Summary

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

## Correlation ID and Errors

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
