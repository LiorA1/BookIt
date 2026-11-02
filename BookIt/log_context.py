"""Request-scoped logging context: the correlation ID, a filter that stamps it on records, and a JSON formatter."""

import json
import logging
from contextvars import ContextVar
from datetime import datetime, timezone

# Set by RequestLoggingMiddleware for the duration of one request; None outside a request.
correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)

# Structured fields passed through `extra=` that JsonFormatter copies into the output.
EXTRA_FIELDS = ("method", "path", "status", "duration_ms")


class CorrelationIdFilter(logging.Filter):
    """Adds the current request's correlation ID to every record that passes through the handler."""

    def filter(self, record):
        record.correlation_id = correlation_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """Renders each record as one JSON object per line; tracebacks go in `exception`."""

    def format(self, record):
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", None),
        }
        for field in EXTRA_FIELDS:
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)
