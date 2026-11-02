import io
import json
import logging
import uuid
from unittest.mock import patch

from django.core.exceptions import BadRequest, PermissionDenied, SuspiciousOperation
from django.http import Http404, HttpRequest
from django.http.multipartparser import MultiPartParserError
from django.test import Client, SimpleTestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .log_context import CorrelationIdFilter, JsonFormatter, correlation_id_var
from .middleware import CORRELATION_ID_HEADER, ExceptionMiddleware

SECRET_DETAIL = "secret internal detail"


class JsonLogCaptureMixin:
    def capture_json_logs(self, logger_name):
        """Attach the project's filter and formatter to a logger and return the stream of JSON lines it writes."""
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.addFilter(CorrelationIdFilter())
        handler.setFormatter(JsonFormatter())
        logger = logging.getLogger(logger_name)
        previous = (logger.level, logger.propagate)

        def restore():
            logger.removeHandler(handler)
            logger.setLevel(previous[0])
            logger.propagate = previous[1]

        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        self.addCleanup(restore)
        return stream

    @staticmethod
    def json_lines(stream):
        return [json.loads(line) for line in stream.getvalue().splitlines()]


class FailingLoginMixin:
    def post_failing_login(self):
        """POST a valid login body while the auth service raises an unexpected error."""
        with patch("accounts.views.AuthService.login", side_effect=RuntimeError(SECRET_DETAIL)):
            return self.client.post(
                reverse("login"), {"email": "user@bookit.test", "password": "irrelevant"}, format="json"
            )


class RequestLoggingMiddlewareTests(JsonLogCaptureMixin, FailingLoginMixin, APITestCase):
    def test_response_carries_a_generated_uuid4_correlation_id(self):
        response = self.client.get(reverse("business-list"))

        correlation_id = response[CORRELATION_ID_HEADER]
        self.assertEqual(uuid.UUID(correlation_id).version, 4)
        self.assertEqual(str(uuid.UUID(correlation_id)), correlation_id)

    def test_each_request_gets_a_new_correlation_id(self):
        first = self.client.get(reverse("business-list"))
        second = self.client.get(reverse("business-list"))

        self.assertNotEqual(first[CORRELATION_ID_HEADER], second[CORRELATION_ID_HEADER])

    def test_client_supplied_correlation_id_is_ignored(self):
        supplied = "attacker-chosen\nid"
        with self.assertLogs("bookit.request", level=logging.INFO) as logs:
            response = self.client.get(reverse("business-list"), headers={CORRELATION_ID_HEADER: supplied})

        self.assertNotEqual(response[CORRELATION_ID_HEADER], supplied)
        self.assertEqual(uuid.UUID(response[CORRELATION_ID_HEADER]).version, 4)
        self.assertNotIn(supplied, logs.output[0])

    def test_correlation_id_is_set_on_error_responses(self):
        unauthorized = self.client.get(reverse("business-list"))
        bad_request = self.client.post(reverse("login"), {}, format="json")

        self.assertEqual(unauthorized.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(bad_request.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(CORRELATION_ID_HEADER, unauthorized)
        self.assertIn(CORRELATION_ID_HEADER, bad_request)

    def test_request_log_has_method_path_status_and_duration(self):
        with self.assertLogs("bookit.request", level=logging.INFO) as logs:
            self.client.get("/admin/login/")

        record = logs.records[0]
        self.assertEqual(record.method, "GET")
        self.assertEqual(record.path, "/admin/login/")
        self.assertEqual(record.status, status.HTTP_200_OK)
        self.assertIsInstance(record.duration_ms, float)
        self.assertGreaterEqual(record.duration_ms, 0)

    def test_request_log_does_not_include_the_query_string(self):
        with self.assertLogs("bookit.request", level=logging.INFO) as logs:
            self.client.get(reverse("business-list"), {"search": "sensitive-value"})

        self.assertEqual(logs.records[0].path, reverse("business-list"))
        self.assertNotIn("sensitive-value", logs.output[0])

    def test_log_level_follows_the_response_status(self):
        with self.assertLogs("bookit.request", level=logging.INFO) as logs:
            self.client.get("/admin/login/")
            self.client.get(reverse("business-list"))
            self.post_failing_login()

        self.assertEqual(
            [(record.status, record.levelno) for record in logs.records],
            [
                (status.HTTP_200_OK, logging.INFO),
                (status.HTTP_401_UNAUTHORIZED, logging.WARNING),
                (status.HTTP_500_INTERNAL_SERVER_ERROR, logging.ERROR),
            ],
        )

    def test_json_log_line_carries_the_response_correlation_id(self):
        stream = self.capture_json_logs("bookit.request")

        response = self.client.get(reverse("business-list"))

        (line,) = self.json_lines(stream)
        self.assertEqual(line["correlation_id"], response[CORRELATION_ID_HEADER])
        self.assertEqual(line["logger"], "bookit.request")
        self.assertEqual(line["level"], "WARNING")
        self.assertEqual(line["method"], "GET")
        self.assertEqual(line["path"], reverse("business-list"))
        self.assertEqual(line["status"], status.HTTP_401_UNAUTHORIZED)
        self.assertIn("duration_ms", line)
        self.assertIn("timestamp", line)

    def test_correlation_id_is_cleared_after_the_request(self):
        self.client.get(reverse("business-list"))

        self.assertIsNone(correlation_id_var.get())


class ExceptionMiddlewareTests(JsonLogCaptureMixin, FailingLoginMixin, APITestCase):
    def test_unexpected_exception_returns_a_generic_json_500(self):
        response = self.post_failing_login()

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response.json(), {"detail": "Internal server error."})
        self.assertIn(CORRELATION_ID_HEADER, response)

    def test_response_does_not_expose_internal_details(self):
        response = self.post_failing_login()

        body = response.content.decode()
        for leaked in (SECRET_DETAIL, "RuntimeError", "Traceback", "accounts/views.py"):
            self.assertNotIn(leaked, body)

    def test_exception_is_logged_server_side_with_its_traceback(self):
        with self.assertLogs("bookit.exception", level=logging.ERROR) as logs:
            self.post_failing_login()

        record = logs.records[0]
        self.assertEqual(record.getMessage(), f"Unhandled exception: POST {reverse('login')}")
        self.assertIsInstance(record.exc_info[1], RuntimeError)
        self.assertIn(SECRET_DETAIL, logs.output[0])
        self.assertIn("Traceback", logs.output[0])

    def test_exception_log_line_carries_the_response_correlation_id_and_traceback(self):
        stream = self.capture_json_logs("bookit.exception")

        response = self.post_failing_login()

        (line,) = self.json_lines(stream)
        self.assertEqual(line["correlation_id"], response[CORRELATION_ID_HEADER])
        self.assertEqual(line["level"], "ERROR")
        self.assertIn("RuntimeError", line["exception"])
        self.assertIn(SECRET_DETAIL, line["exception"])

    def test_unexpected_exception_is_not_logged_as_a_successful_request(self):
        with self.assertLogs("bookit.request", level=logging.INFO) as logs:
            self.post_failing_login()

        self.assertEqual(logs.records[0].status, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(logs.records[0].levelno, logging.ERROR)

    @override_settings(DEBUG=True)
    def test_debug_logs_the_exception_and_lets_django_render_its_debug_page(self):
        # Django's own django.request logger also reports the exception when it renders the debug page; capture it
        # here to keep the test output clean.
        with self.assertLogs("django.request", level=logging.ERROR):
            with self.assertLogs("bookit.exception", level=logging.ERROR) as logs:
                with self.assertRaises(RuntimeError):
                    self.post_failing_login()

        self.assertIn(SECRET_DETAIL, logs.output[0])

    def test_api_errors_handled_by_drf_are_not_turned_into_500(self):
        with self.assertNoLogs("bookit.exception", level=logging.ERROR):
            response = self.client.post(reverse("login"), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class FailingMiddleware:
    """Test-only middleware that fails before the view runs, like a session store outage would."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        raise RuntimeError(SECRET_DETAIL)


@override_settings(
    MIDDLEWARE=[
        "BookIt.middleware.RequestLoggingMiddleware",
        "BookIt.middleware.ExceptionMiddleware",
        "BookIt.tests.FailingMiddleware",
    ]
)
class Handler500Tests(SimpleTestCase):
    def get_with_failing_middleware(self, path):
        client = Client(raise_request_exception=False)
        # Django's own django.request logger reports the exception; capture it to keep the test output clean.
        with self.assertLogs("django.request", level=logging.ERROR):
            return client.get(path)

    def test_middleware_exception_returns_the_generic_json_500(self):
        for path in (reverse("business-list"), "/admin/login/"):
            with self.subTest(path=path):
                response = self.get_with_failing_middleware(path)

                self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
                self.assertEqual(response["Content-Type"], "application/json")
                self.assertEqual(response.json(), {"detail": "Internal server error."})
                self.assertIn(CORRELATION_ID_HEADER, response)

    def test_middleware_exception_response_does_not_expose_internal_details(self):
        response = self.get_with_failing_middleware(reverse("business-list"))

        body = response.content.decode()
        for leaked in (SECRET_DETAIL, "RuntimeError", "Traceback", "BookIt/tests.py"):
            self.assertNotIn(leaked, body)


class ExceptionMiddlewareHandledExceptionTests(SimpleTestCase):
    def test_exceptions_django_maps_to_4xx_are_left_alone_and_not_logged(self):
        middleware = ExceptionMiddleware(lambda request: None)
        request = HttpRequest()
        request.method = "GET"
        request.path = "/somewhere/"

        for exception in (Http404(), PermissionDenied(), SuspiciousOperation(), BadRequest(), MultiPartParserError()):
            with self.subTest(exception=type(exception).__name__):
                with self.assertNoLogs("bookit.exception", level=logging.ERROR):
                    self.assertIsNone(middleware.process_exception(request, exception))
