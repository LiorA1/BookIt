import logging
import time
import uuid

from django.conf import settings
from django.core.exceptions import BadRequest, PermissionDenied, SuspiciousOperation
from django.http import Http404, JsonResponse
from django.http.multipartparser import MultiPartParserError

from .log_context import correlation_id_var

CORRELATION_ID_HEADER = "X-Correlation-ID"

request_logger = logging.getLogger("bookit.request")
exception_logger = logging.getLogger("bookit.exception")

# Exceptions Django already turns into proper 4xx responses; they are not server errors.
HANDLED_BY_DJANGO = (Http404, PermissionDenied, SuspiciousOperation, BadRequest, MultiPartParserError)


class RequestLoggingMiddleware:
    """Gives each request a server-generated correlation ID, logs one line when it finishes, and echoes the ID.

    The ID is never read from the client, so it cannot be used to inject text into the logs. Keep this middleware
    first in MIDDLEWARE: it then times everything and puts the header on every response, including a generic 500.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        correlation_id = str(uuid.uuid4())
        token = correlation_id_var.set(correlation_id)
        request.correlation_id = correlation_id
        started = time.perf_counter()
        try:
            response = self.get_response(request)
            response[CORRELATION_ID_HEADER] = correlation_id
            request_logger.log(
                self._level_for(response.status_code),
                "request completed",
                # request.path excludes the query string, whose values may be sensitive.
                extra={
                    "method": request.method,
                    "path": request.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            return response
        finally:
            correlation_id_var.reset(token)

    @staticmethod
    def _level_for(status_code):
        if status_code >= 500:
            return logging.ERROR
        if status_code >= 400:
            return logging.WARNING
        return logging.INFO


class ExceptionMiddleware:
    """Logs unexpected view exceptions with their traceback and answers with a generic JSON 500.

    Django wraps every middleware in its own exception handler, so only `process_exception` sees view exceptions; a
    try/except around `get_response` would never run. Exceptions raised by other middleware are not covered here.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if isinstance(exception, HANDLED_BY_DJANGO):
            return None

        exception_logger.error(
            "Unhandled exception: %s %s",
            request.method,
            request.path,
            exc_info=(type(exception), exception, exception.__traceback__),
        )
        if settings.DEBUG:
            # Let Django render its debug page for developers; the exception is already logged above.
            return None
        # Never include the traceback, the exception text, or any internal detail in the body.
        return JsonResponse({"detail": "Internal server error."}, status=500)
