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


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("service", "client", "start_time", "status")
    list_filter = ("status", "start_time")
    search_fields = ("service__name", "client__email")
