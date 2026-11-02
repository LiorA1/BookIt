from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import Role

from .exceptions import SlotUnavailableError, StartTimeInPastError, StartTimeTooFarError
from .models import Appointment

OVERLAP_CONSTRAINT = "appointment_service_no_overlap"


class AppointmentService:
    def __init__(self, appointment_model=None, now=timezone.now, max_advance=None):
        self.appointment_model = appointment_model or Appointment
        self.now = now
        self.max_advance = max_advance or timedelta(days=settings.BOOKING_MAX_ADVANCE_DAYS)

    def book(self, *, client, service, start_time) -> Appointment:
        """Create a Pending appointment for `client`; the database constraint decides slot conflicts."""
        now = self.now()
        if start_time <= now:
            raise StartTimeInPastError()
        # Checked before any date arithmetic: start_time + duration overflows near datetime.max.
        if start_time > now + self.max_advance:
            raise StartTimeTooFarError()

        end_time = start_time + timedelta(minutes=service.duration_minutes)
        try:
            with transaction.atomic():
                return self.appointment_model.objects.create(
                    service=service, client=client, start_time=start_time, end_time=end_time
                )
        except IntegrityError as exc:
            # The exclusion constraint is the source of truth when two requests race for overlapping time.
            if getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None) == OVERLAP_CONSTRAINT:
                raise SlotUnavailableError() from exc
            raise

    def list_for_user(self, user, *, start_time=None, end_time=None, statuses=None):
        """Appointments visible to `user` from current database ownership, ordered by start time.

        `start_time` and `end_time` are inclusive lower and upper bounds on the appointments' start_time.
        """
        # Only the columns AppointmentResponseSerializer renders; keeps the client's password hash and email out of
        # the query. Keep it in sync with the serializer (the list API query tests catch drift).
        queryset = self.appointment_model.objects.select_related("service__business", "client").only(
            "id",
            "status",
            "start_time",
            "end_time",
            "service__id",
            "service__name",
            "service__duration_minutes",
            "service__price",
            "service__business__id",
            "service__business__name",
            "service__business__category",
            "client__id",
            "client__full_name",
        )
        if user.role == Role.Client:
            queryset = queryset.filter(client=user)
        else:
            queryset = queryset.filter(service__business__owner=user)

        if start_time is not None:
            queryset = queryset.filter(start_time__gte=start_time)
        if end_time is not None:
            queryset = queryset.filter(start_time__lte=end_time)
        if statuses:
            queryset = queryset.filter(status__in=statuses)
        # A deterministic ordering keeps pages stable.
        return queryset.order_by("start_time", "id")
