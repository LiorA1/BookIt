from django.contrib import admin

from .models import Appointment, Business, Service


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "category")
    list_filter = ("category",)
    search_fields = ("name", "owner__email")


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "business", "duration_minutes", "price")
    list_filter = ("business",)
    search_fields = ("name", "business__name")
    # Paginated changelist and autocomplete results need a deterministic order.
    ordering = ("id",)

    def get_queryset(self, request):
        # Service.__str__ reads business.name; this also serves the appointment form's autocomplete results.
        return super().get_queryset(request).select_related("business")


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("service", "client", "start_time", "end_time", "status")
    # Left out of the form so Appointment.save() derives it from the service duration.
    readonly_fields = ("end_time",)
    # Ajax lookups instead of dropdowns that render every service and user (one query per service otherwise).
    autocomplete_fields = ("service", "client")
    list_filter = ("status", "start_time")
    search_fields = ("service__name", "client__email")
