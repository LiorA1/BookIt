from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class Category(models.IntegerChoices):
    Barbers = 0, "Barbers"
    Tutors = 1, "Tutors"


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


class Appointment(models.Model):
    class AppointmentStatus(models.IntegerChoices):
        Pending = 0
        Confirmed = 1
        Cancelled = 2

    service = models.ForeignKey(to=Service, related_name="appointments", on_delete=models.CASCADE)
    client = models.ForeignKey(to=settings.AUTH_USER_MODEL, related_name="appointments", on_delete=models.CASCADE)
    start_time = models.DateTimeField()
    status = models.IntegerField(choices=AppointmentStatus.choices, default=AppointmentStatus.Pending.value)

    def __str__(self):
        return f"{self.service.name} - {self.client} @ {self.start_time:%Y-%m-%d %H:%M}"
