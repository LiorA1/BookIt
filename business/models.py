from datetime import timedelta

from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import RangeBoundary, RangeOperators
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from .db_functions import BigIntPointRange, TsTzRange


class Category(models.IntegerChoices):
    Barbers = 0
    Tutors = 1


class Business(models.Model):
    name = models.CharField(_("business name"), max_length=150, blank=False, db_index=True)
    owner = models.ForeignKey(to=settings.AUTH_USER_MODEL, related_name="businesses", on_delete=models.CASCADE)
    category = models.IntegerField(choices=Category.choices, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["category", "name"], name="business_category_name_idx"),
        ]

    def __str__(self):
        return self.name


class Service(models.Model):
    business = models.ForeignKey(to=Business, related_name="services", on_delete=models.CASCADE)
    name = models.CharField(_("service name"), max_length=150, blank=False)
    duration_minutes = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.name} ({self.business.name})"


class AppointmentStatus(models.IntegerChoices):
    Pending = 0
    Confirmed = 1
    Cancelled = 2


class Appointment(models.Model):
    service = models.ForeignKey(to=Service, related_name="appointments", on_delete=models.CASCADE)
    client = models.ForeignKey(to=settings.AUTH_USER_MODEL, related_name="appointments", on_delete=models.CASCADE)
    start_time = models.DateTimeField()
    # Snapshot of start_time + the service duration at booking time; later duration edits do not move it.
    end_time = models.DateTimeField()
    status = models.IntegerField(choices=AppointmentStatus.choices, default=AppointmentStatus.Pending.value)

    class Meta:
        constraints = [
            # No two active appointments of one service may overlap in time. Back-to-back is allowed because the
            # range is half-open, and a cancelled appointment frees its slot. The database is the final defense
            # against double booking, including races between concurrent requests.
            ExclusionConstraint(
                name="appointment_service_no_overlap",
                expressions=[
                    (BigIntPointRange("service", "service", RangeBoundary(inclusive_upper=True)), RangeOperators.OVERLAPS),
                    (TsTzRange("start_time", "end_time", RangeBoundary()), RangeOperators.OVERLAPS),
                ],
                condition=~models.Q(status=AppointmentStatus.Cancelled),
            ),
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="appointment_end_after_start",
            ),
        ]

    def save(self, *args, **kwargs):
        # Fallback for write paths that skip AppointmentService (admin, shell); the service sets end_time itself.
        if self.end_time is None and self.start_time is not None:
            self.end_time = self.start_time + timedelta(minutes=self.service.duration_minutes)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.service.name} - {self.client} @ {self.start_time:%Y-%m-%d %H:%M}"
