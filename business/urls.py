from django.urls import path

from .views import BusinessListView, BusinessSummaryView

urlpatterns = [
    path("", BusinessListView.as_view(), name="business-list"),
    path("<int:pk>/summary/", BusinessSummaryView.as_view(), name="business-summary"),
]
