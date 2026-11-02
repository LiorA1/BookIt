from django.urls import path

from .views import AppointmentListCreateView

urlpatterns = [
    path("", AppointmentListCreateView.as_view(), name="appointment-list"),
]
