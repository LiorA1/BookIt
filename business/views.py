from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.filters import SearchFilter
from rest_framework.generics import GenericAPIView, ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import IsBusinessOwner, IsClient

from .exceptions import (
    BusinessNotOwnedError,
    SlotUnavailableError,
    StartTimeInPastError,
    StartTimeTooFarError,
)
from .models import Business
from .pagination import StandardPageNumberPagination
from .serializers import (
    AppointmentCreateRequestSerializer,
    AppointmentListQuerySerializer,
    AppointmentResponseSerializer,
    BusinessListQuerySerializer,
    BusinessResponseSerializer,
    BusinessSummaryItemResponseSerializer,
)
from .services import AppointmentService, BusinessSummaryService


class BusinessListView(ListAPIView):
    """GET /api/businesses/ - paginated list of businesses (?page=, ?page_size=, ?category=, ?search=)."""

    serializer_class = BusinessResponseSerializer
    pagination_class = StandardPageNumberPagination
    filter_backends = [SearchFilter]
    search_fields = ["name"]

    def get_queryset(self):
        query = BusinessListQuerySerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)

        # A deterministic ordering keeps pages stable and avoids DRF's UnorderedObjectListWarning.
        # Only the columns BusinessResponseSerializer renders; keeps the owner's password hash and email out of the
        # query. Keep it in sync with the serializer (test_query_count_does_not_grow_with_businesses catches drift).
        queryset = (
            Business.objects.select_related("owner")
            .only("id", "name", "category", "owner__id", "owner__full_name")
            .order_by("id")
        )
        if "category" in query.validated_data:
            queryset = queryset.filter(category=query.validated_data["category"])
        return queryset


class AppointmentListCreateView(GenericAPIView):
    """Appointments: GET lists the caller's own (?from=, ?to=, ?status=, ?page=); POST books one (Client only)."""

    serializer_class = AppointmentResponseSerializer
    pagination_class = StandardPageNumberPagination
    appointment_service_class = AppointmentService

    def get_permissions(self):
        permission_classes = (
            [IsAuthenticated, IsClient]
            if self.request.method == "POST"
            else [IsAuthenticated]
        )
        return [permission() for permission in permission_classes]

    def get(self, request):
        query = AppointmentListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)

        appointments = self.appointment_service_class().list_for_user(
            request.user, **query.validated_data
        )
        page = self.paginate_queryset(appointments)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    def post(self, request):
        serializer = AppointmentCreateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            appointment = self.appointment_service_class().book(
                client=request.user, **serializer.validated_data
            )
        except StartTimeInPastError:
            return Response(
                {"start_time": ["Appointments cannot be booked in the past."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except StartTimeTooFarError:
            return Response(
                {"start_time": ["Appointments cannot be booked that far ahead."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except SlotUnavailableError:
            return Response(
                {"start_time": ["This time slot is already booked."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            self.get_serializer(appointment).data, status=status.HTTP_201_CREATED
        )


class BusinessSummaryView(GenericAPIView):
    """GET /api/businesses/<id>/summary/ - owner-only, paginated per-service count and expected revenue."""

    serializer_class = BusinessSummaryItemResponseSerializer
    pagination_class = StandardPageNumberPagination
    permission_classes = [IsAuthenticated, IsBusinessOwner]
    summary_service_class = BusinessSummaryService

    def get(self, request, pk):
        business = get_object_or_404(Business.objects.only("id", "owner"), pk=pk)
        try:
            summary = self.summary_service_class().summarize(
                request_owner=request.user, business=business
            )
        except BusinessNotOwnedError:
            return Response(
                {"detail": "You do not have permission to view this business."},
                status=status.HTTP_403_FORBIDDEN,
            )

        page = self.paginate_queryset(summary)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)
