from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal
from io import StringIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.backends import TokenBackend
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import Role

from .exceptions import BusinessNotOwnedError, SlotUnavailableError, StartTimeInPastError, StartTimeTooFarError
from .models import Appointment, AppointmentStatus, Business, Category, Service
from .services import AppointmentService, BusinessSummaryService

User = get_user_model()


class BusinessListApiTests(APITestCase):
    url = reverse("business-list")

    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@example.com", password="S3cure-pass!", full_name="Yossi Cohen", role=Role.BusinessOwner
        )
        self.client.force_authenticate(self.owner)

    def create_businesses(self, count):
        Business.objects.bulk_create(
            Business(name=f"Business {i}", owner=self.owner, category=Category.Barbers) for i in range(count)
        )

    def test_requires_authentication(self):
        self.client.force_authenticate(None)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def get_with_bearer(self, token):
        self.client.force_authenticate(None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return self.client.get(self.url)

    def test_valid_access_token_is_accepted(self):
        response = self.get_with_bearer(AccessToken.for_user(self.owner))

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_malformed_token_returns_401(self):
        response = self.get_with_bearer("not-a-jwt")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_token_with_wrong_signature_returns_401(self):
        payload = dict(AccessToken.for_user(self.owner).payload)
        forged = TokenBackend("HS256", signing_key="a-different-signing-key-of-sufficient-length").encode(payload)

        response = self.get_with_bearer(forged)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_expired_token_returns_401(self):
        token = AccessToken.for_user(self.owner)
        token.set_exp(lifetime=-timedelta(seconds=1))

        response = self.get_with_bearer(token)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_returns_paginated_envelope(self):
        business = Business.objects.create(name="Fade Masters", owner=self.owner, category=Category.Barbers)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data), {"count", "next", "previous", "results"})
        self.assertEqual(response.data["count"], 1)
        self.assertIsNone(response.data["next"])
        self.assertEqual(
            response.data["results"],
            [
                {
                    "id": business.id,
                    "name": "Fade Masters",
                    "category": "barbers",
                    "owner": {"id": self.owner.id, "full_name": "Yossi Cohen"},
                }
            ],
        )

    def test_default_page_size(self):
        self.create_businesses(25)

        response = self.client.get(self.url)

        self.assertEqual(response.data["count"], 25)
        self.assertEqual(len(response.data["results"]), 20)
        self.assertIsNotNone(response.data["next"])
        self.assertIsNone(response.data["previous"])

    def test_second_page(self):
        self.create_businesses(25)

        response = self.client.get(self.url, {"page": 2})

        self.assertEqual(len(response.data["results"]), 5)
        self.assertEqual(response.data["results"][0]["name"], "Business 20")
        self.assertIsNone(response.data["next"])
        self.assertIsNotNone(response.data["previous"])

    def test_custom_page_size_is_capped(self):
        self.create_businesses(105)

        self.assertEqual(len(self.client.get(self.url, {"page_size": 5}).data["results"]), 5)
        self.assertEqual(len(self.client.get(self.url, {"page_size": 500}).data["results"]), 100)

    def test_out_of_range_page_returns_404(self):
        self.create_businesses(3)

        response = self.client.get(self.url, {"page": 99})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_filter_by_category(self):
        Business.objects.create(name="Fade Masters", owner=self.owner, category=Category.Barbers)
        Business.objects.create(name="Math Pro", owner=self.owner, category=Category.Tutors)

        response = self.client.get(self.url, {"category": "tutors"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([b["name"] for b in response.data["results"]], ["Math Pro"])

    def test_invalid_category_returns_400(self):
        response = self.client.get(self.url, {"category": "plumbers"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("category", response.data)

    def test_capitalized_category_returns_400(self):
        response = self.client.get(self.url, {"category": "Tutors"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("category", response.data)

    def test_query_count_does_not_grow_with_businesses(self):
        self.create_businesses(1)
        with CaptureQueriesContext(connection) as one_business:
            self.client.get(self.url)

        self.create_businesses(9)
        with CaptureQueriesContext(connection) as ten_businesses:
            response = self.client.get(self.url)

        self.assertEqual(len(response.data["results"]), 10)
        self.assertEqual(len(ten_businesses), len(one_business))

    def test_query_does_not_fetch_owner_credentials(self):
        self.create_businesses(1)

        with CaptureQueriesContext(connection) as queries:
            self.client.get(self.url)

        # The pagination COUNT query runs first and selects no columns, so look at the row query specifically.
        business_query = next(
            q["sql"] for q in queries if '"business_business"' in q["sql"] and "COUNT(" not in q["sql"]
        )
        self.assertIn('"full_name"', business_query)
        self.assertNotIn("password", business_query)
        self.assertNotIn('"email"', business_query)

    def test_search_by_name_is_case_insensitive_substring(self):
        Business.objects.create(name="Fade Masters", owner=self.owner, category=Category.Barbers)
        Business.objects.create(name="Math Pro", owner=self.owner, category=Category.Tutors)

        response = self.client.get(self.url, {"search": "fade"})

        self.assertEqual([b["name"] for b in response.data["results"]], ["Fade Masters"])

    def test_filters_combine_and_paginate_over_filtered_set(self):
        self.create_businesses(25)
        Business.objects.bulk_create(
            Business(name=f"Tutor {i}", owner=self.owner, category=Category.Tutors) for i in range(3)
        )

        Business.objects.create(name="Tutor Barbershop", owner=self.owner, category=Category.Barbers)
        params = {"category": "barbers", "search": "business", "page_size": 10}

        response = self.client.get(self.url, params)

        self.assertEqual(response.data["count"], 25)
        self.assertEqual(len(response.data["results"]), 10)
        self.assertIn("category=barbers", response.data["next"])
        self.assertIn("search=business", response.data["next"])
        self.assertIn("page=2", response.data["next"])

        last_page = self.client.get(self.url, {**params, "page": 3})
        self.assertEqual(len(last_page.data["results"]), 5)
        self.assertIsNone(last_page.data["next"])

    def test_multi_word_search_requires_all_terms(self):
        Business.objects.create(name="Fade Masters Barbershop", owner=self.owner, category=Category.Barbers)
        Business.objects.create(name="Fade Studio", owner=self.owner, category=Category.Barbers)

        response = self.client.get(self.url, {"search": "masters fade"})

        self.assertEqual([b["name"] for b in response.data["results"]], ["Fade Masters Barbershop"])


class AppointmentFixtureMixin:
    """Readable helpers shared by the appointment service and API tests."""

    def create_user(self, email, role):
        return User.objects.create_user(email=email, password="S3cure-pass!", full_name=email.split("@")[0], role=role)

    def create_service(self, owner, *, name="Haircut", duration_minutes=30, price="80.00", business_name="Fade Masters"):
        business = Business.objects.create(name=business_name, owner=owner, category=Category.Barbers)
        return Service.objects.create(
            business=business, name=name, duration_minutes=duration_minutes, price=Decimal(price)
        )

    @staticmethod
    def future(days=1, *, minutes=0):
        return (timezone.now() + timedelta(days=days, minutes=minutes)).replace(microsecond=0)

    @staticmethod
    def iso(value):
        return value.isoformat().replace("+00:00", "Z")


class AppointmentServiceTests(AppointmentFixtureMixin, TestCase):
    def setUp(self):
        self.owner = self.create_user("owner@example.com", Role.BusinessOwner)
        self.client_user = self.create_user("client@example.com", Role.Client)
        self.service = self.create_service(self.owner)
        self.appointments = AppointmentService()

    def test_book_creates_pending_appointment_with_end_time_from_duration(self):
        start = self.future()

        appointment = self.appointments.book(client=self.client_user, service=self.service, start_time=start)

        appointment.refresh_from_db()
        self.assertEqual(appointment.status, AppointmentStatus.Pending)
        self.assertEqual(appointment.client, self.client_user)
        self.assertEqual(appointment.start_time, start)
        self.assertEqual(appointment.end_time, start + timedelta(minutes=30))

    def test_book_rejects_start_time_in_the_past(self):
        fixed_now = self.future()
        appointments = AppointmentService(now=lambda: fixed_now)

        with self.assertRaises(StartTimeInPastError):
            appointments.book(client=self.client_user, service=self.service, start_time=fixed_now)

        self.assertFalse(Appointment.objects.exists())

    def test_book_allows_start_time_exactly_at_the_booking_horizon(self):
        fixed_now = self.future()
        appointments = AppointmentService(now=lambda: fixed_now, max_advance=timedelta(days=30))

        appointment = appointments.book(
            client=self.client_user, service=self.service, start_time=fixed_now + timedelta(days=30)
        )

        self.assertEqual(appointment.start_time, fixed_now + timedelta(days=30))

    def test_book_rejects_start_time_beyond_the_booking_horizon(self):
        fixed_now = self.future()
        appointments = AppointmentService(now=lambda: fixed_now, max_advance=timedelta(days=30))

        with self.assertRaises(StartTimeTooFarError):
            appointments.book(
                client=self.client_user,
                service=self.service,
                start_time=fixed_now + timedelta(days=30, seconds=1),
            )

        self.assertFalse(Appointment.objects.exists())

    def test_book_rejects_start_time_near_datetime_max_instead_of_overflowing(self):
        far_future = datetime.max.replace(tzinfo=dt_timezone.utc, microsecond=0)

        with self.assertRaises(StartTimeTooFarError):
            self.appointments.book(client=self.client_user, service=self.service, start_time=far_future)

    def test_book_same_slot_twice_raises_slot_unavailable(self):
        start = self.future()
        self.appointments.book(client=self.client_user, service=self.service, start_time=start)
        other_client = self.create_user("other@example.com", Role.Client)

        with self.assertRaises(SlotUnavailableError):
            self.appointments.book(client=other_client, service=self.service, start_time=start)

        self.assertEqual(Appointment.objects.count(), 1)

    def test_book_overlapping_start_inside_existing_appointment_raises_slot_unavailable(self):
        start = self.future()
        self.appointments.book(client=self.client_user, service=self.service, start_time=start)

        with self.assertRaises(SlotUnavailableError):
            self.appointments.book(
                client=self.client_user, service=self.service, start_time=start + timedelta(minutes=15)
            )

        self.assertEqual(Appointment.objects.count(), 1)

    def test_book_ending_inside_existing_appointment_raises_slot_unavailable(self):
        start = self.future()
        self.appointments.book(client=self.client_user, service=self.service, start_time=start)

        with self.assertRaises(SlotUnavailableError):
            self.appointments.book(
                client=self.client_user, service=self.service, start_time=start - timedelta(minutes=15)
            )

    def test_longer_service_covering_an_existing_appointment_raises_slot_unavailable(self):
        start = self.future()
        self.appointments.book(client=self.client_user, service=self.service, start_time=start)
        self.service.duration_minutes = 90
        self.service.save()

        with self.assertRaises(SlotUnavailableError):
            self.appointments.book(
                client=self.client_user, service=self.service, start_time=start - timedelta(minutes=30)
            )

    def test_back_to_back_appointments_are_allowed(self):
        start = self.future()
        self.appointments.book(client=self.client_user, service=self.service, start_time=start)

        self.appointments.book(client=self.client_user, service=self.service, start_time=start + timedelta(minutes=30))
        self.appointments.book(client=self.client_user, service=self.service, start_time=start - timedelta(minutes=30))

        self.assertEqual(Appointment.objects.count(), 3)

    def test_overlap_with_a_cancelled_appointment_is_allowed(self):
        start = self.future()
        first = self.appointments.book(client=self.client_user, service=self.service, start_time=start)
        Appointment.objects.filter(pk=first.pk).update(status=AppointmentStatus.Cancelled)

        self.appointments.book(client=self.client_user, service=self.service, start_time=start + timedelta(minutes=15))

        self.assertEqual(Appointment.objects.count(), 2)

    def test_cancelled_appointment_frees_the_slot(self):
        start = self.future()
        first = self.appointments.book(client=self.client_user, service=self.service, start_time=start)
        Appointment.objects.filter(pk=first.pk).update(status=AppointmentStatus.Cancelled)

        second = self.appointments.book(client=self.client_user, service=self.service, start_time=start)

        self.assertNotEqual(first.pk, second.pk)

    def test_same_start_time_on_a_different_service_is_allowed(self):
        start = self.future()
        other_service = self.create_service(self.owner, name="Beard trim", business_name="Razor Edge")
        self.appointments.book(client=self.client_user, service=self.service, start_time=start)

        self.appointments.book(client=self.client_user, service=other_service, start_time=start)

        self.assertEqual(Appointment.objects.count(), 2)

    def test_database_constraint_rejects_duplicate_active_slot_without_the_service(self):
        start = self.future()
        Appointment.objects.create(service=self.service, client=self.client_user, start_time=start)

        with self.assertRaises(IntegrityError), transaction.atomic():
            Appointment.objects.create(service=self.service, client=self.client_user, start_time=start)

    def test_database_constraint_rejects_partial_overlap_without_the_service(self):
        start = self.future()
        Appointment.objects.create(service=self.service, client=self.client_user, start_time=start)

        with self.assertRaises(IntegrityError), transaction.atomic():
            Appointment.objects.create(
                service=self.service, client=self.client_user, start_time=start + timedelta(minutes=10)
            )

    def test_database_constraint_allows_overlap_on_a_different_service(self):
        start = self.future()
        other_service = self.create_service(self.owner, name="Beard trim", business_name="Razor Edge")
        Appointment.objects.create(service=self.service, client=self.client_user, start_time=start)

        Appointment.objects.create(service=other_service, client=self.client_user, start_time=start)

        self.assertEqual(Appointment.objects.count(), 2)

    def test_database_constraint_rejects_end_time_not_after_start_time(self):
        start = self.future()

        with self.assertRaises(IntegrityError), transaction.atomic():
            Appointment.objects.create(
                service=self.service, client=self.client_user, start_time=start, end_time=start
            )

    def test_save_fills_missing_end_time_from_service_duration(self):
        start = self.future()

        appointment = Appointment.objects.create(service=self.service, client=self.client_user, start_time=start)

        self.assertEqual(appointment.end_time, start + timedelta(minutes=30))

    def test_list_for_client_returns_only_own_appointments(self):
        other_client = self.create_user("other@example.com", Role.Client)
        mine = Appointment.objects.create(service=self.service, client=self.client_user, start_time=self.future())
        Appointment.objects.create(service=self.service, client=other_client, start_time=self.future(2))

        self.assertEqual(list(self.appointments.list_for_user(self.client_user)), [mine])

    def test_list_for_owner_returns_only_appointments_of_owned_businesses(self):
        other_owner = self.create_user("rival@example.com", Role.BusinessOwner)
        rival_service = self.create_service(other_owner, business_name="Rival Cuts")
        mine = Appointment.objects.create(service=self.service, client=self.client_user, start_time=self.future())
        Appointment.objects.create(service=rival_service, client=self.client_user, start_time=self.future(2))

        self.assertEqual(list(self.appointments.list_for_user(self.owner)), [mine])
        self.assertEqual(self.appointments.list_for_user(self.create_user("new@example.com", Role.BusinessOwner)).count(), 0)

    def test_list_is_ordered_by_start_time_then_id(self):
        later = Appointment.objects.create(service=self.service, client=self.client_user, start_time=self.future(3))
        earlier = Appointment.objects.create(service=self.service, client=self.client_user, start_time=self.future(1))

        self.assertEqual(list(self.appointments.list_for_user(self.client_user)), [earlier, later])


class AppointmentCreateApiTests(AppointmentFixtureMixin, APITestCase):
    url = reverse("appointment-list")

    def setUp(self):
        self.owner = self.create_user("owner@example.com", Role.BusinessOwner)
        self.client_user = self.create_user("client@example.com", Role.Client)
        self.service = self.create_service(self.owner)
        self.client.force_authenticate(self.client_user)

    def book(self, **overrides):
        payload = {"service": self.service.pk, "start_time": self.iso(self.future()), **overrides}
        return self.client.post(self.url, payload, format="json")

    def test_requires_authentication(self):
        self.client.force_authenticate(None)

        response = self.book()

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_business_owner_gets_403(self):
        self.client.force_authenticate(self.owner)

        response = self.book()

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Appointment.objects.exists())

    def test_role_is_checked_against_the_database_not_the_token_claim(self):
        token = AccessToken.for_user(self.client_user)
        token["role"] = "Client"
        User.objects.filter(pk=self.client_user.pk).update(role=Role.BusinessOwner)
        self.client.force_authenticate(None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.book()

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_client_books_appointment_and_gets_201_with_schema(self):
        start = self.future()

        response = self.book(start_time=self.iso(start))

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        appointment = Appointment.objects.get()
        self.assertEqual(
            response.data,
            {
                "id": appointment.pk,
                "status": "pending",
                "start_time": self.iso(start),
                "end_time": self.iso(start + timedelta(minutes=30)),
                "service": {"id": self.service.pk, "name": "Haircut", "duration_minutes": 30, "price": "80.00"},
                "business": {"id": self.service.business.pk, "name": "Fade Masters", "category": "barbers"},
                "client": {"id": self.client_user.pk, "full_name": "client"},
            },
        )

    def test_offset_start_time_is_stored_as_the_same_instant(self):
        start = self.future()
        local = start.astimezone(timezone.get_fixed_timezone(120)).isoformat()

        response = self.book(start_time=local)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Appointment.objects.get().start_time, start)

    def test_missing_fields_return_field_errors(self):
        response = self.client.post(self.url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(set(response.data), {"service", "start_time"})

    def test_unknown_service_returns_400_on_service(self):
        response = self.book(service=999999)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["service"], ["Service not found."])

    def test_non_integer_service_returns_400_on_service(self):
        response = self.book(service="abc")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("service", response.data)

    def test_naive_start_time_returns_400_on_start_time(self):
        response = self.book(start_time="2099-01-01T10:00:00")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("start_time", response.data)

    def test_invalid_start_time_returns_400_on_start_time(self):
        response = self.book(start_time="tomorrow")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("start_time", response.data)

    def test_start_time_in_the_past_returns_400_on_start_time(self):
        response = self.book(start_time=self.iso(self.future(-1)))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("start_time", response.data)
        self.assertFalse(Appointment.objects.exists())

    def test_start_time_beyond_the_booking_horizon_returns_400_on_start_time(self):
        response = self.book(start_time=self.iso(self.future(days=settings.BOOKING_MAX_ADVANCE_DAYS + 1)))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, {"start_time": ["Appointments cannot be booked that far ahead."]})
        self.assertFalse(Appointment.objects.exists())

    def test_start_time_near_the_year_9999_returns_400_not_500(self):
        for value in ("9999-12-31T23:59:59Z", "9999-12-31T23:40:00Z", "9999-12-31T23:59:59-02:00"):
            with self.subTest(start_time=value):
                response = self.book(start_time=value)

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("start_time", response.data)

    def test_booked_slot_returns_400_on_start_time(self):
        start = self.iso(self.future())
        self.book(start_time=start)
        other_client = self.create_user("other@example.com", Role.Client)
        self.client.force_authenticate(other_client)

        response = self.book(start_time=start)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, {"start_time": ["This time slot is already booked."]})
        self.assertEqual(Appointment.objects.count(), 1)

    def test_overlapping_time_returns_400_and_adjacent_time_returns_201(self):
        start = self.future()
        self.book(start_time=self.iso(start))
        self.client.force_authenticate(self.create_user("other@example.com", Role.Client))

        overlapping = self.book(start_time=self.iso(start + timedelta(minutes=15)))
        adjacent = self.book(start_time=self.iso(start + timedelta(minutes=30)))

        self.assertEqual(overlapping.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(overlapping.data, {"start_time": ["This time slot is already booked."]})
        self.assertEqual(adjacent.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Appointment.objects.count(), 2)

    def test_slot_can_be_rebooked_after_cancellation(self):
        start = self.iso(self.future())
        self.book(start_time=start)
        Appointment.objects.update(status=AppointmentStatus.Cancelled)

        response = self.book(start_time=start)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_client_cannot_set_status(self):
        response = self.book(status="Confirmed")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Appointment.objects.get().status, AppointmentStatus.Pending)


class AppointmentListApiTests(AppointmentFixtureMixin, APITestCase):
    url = reverse("appointment-list")

    def setUp(self):
        self.owner = self.create_user("owner@example.com", Role.BusinessOwner)
        self.rival_owner = self.create_user("rival@example.com", Role.BusinessOwner)
        self.client_user = self.create_user("client@example.com", Role.Client)
        self.other_client = self.create_user("other@example.com", Role.Client)
        self.service = self.create_service(self.owner)
        self.rival_service = self.create_service(self.rival_owner, business_name="Rival Cuts")
        self.client.force_authenticate(self.client_user)

    def create_appointment(self, *, client=None, service=None, days=1, minutes=0, status=AppointmentStatus.Pending):
        return Appointment.objects.create(
            service=service or self.service,
            client=client or self.client_user,
            start_time=self.future(days, minutes=minutes),
            status=status,
        )

    def ids(self, response):
        return [item["id"] for item in response.data["results"]]

    def test_requires_authentication(self):
        self.client.force_authenticate(None)

        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_returns_paginated_envelope_and_item_schema(self):
        appointment = self.create_appointment()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data), {"count", "next", "previous", "results"})
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0],
            {
                "id": appointment.pk,
                "status": "pending",
                "start_time": self.iso(appointment.start_time),
                "end_time": self.iso(appointment.end_time),
                "service": {"id": self.service.pk, "name": "Haircut", "duration_minutes": 30, "price": "80.00"},
                "business": {"id": self.service.business.pk, "name": "Fade Masters", "category": "barbers"},
                "client": {"id": self.client_user.pk, "full_name": "client"},
            },
        )

    def test_client_sees_only_own_appointments(self):
        mine = self.create_appointment()
        self.create_appointment(client=self.other_client, days=2)

        response = self.client.get(self.url)

        self.assertEqual(self.ids(response), [mine.pk])

    def test_owner_sees_appointments_for_owned_businesses_of_any_client(self):
        first = self.create_appointment(client=self.client_user, days=1)
        second = self.create_appointment(client=self.other_client, days=2)
        self.create_appointment(service=self.rival_service, days=3)
        self.client.force_authenticate(self.owner)

        response = self.client.get(self.url)

        self.assertEqual(self.ids(response), [first.pk, second.pk])

    def test_owner_cannot_see_another_owners_appointments(self):
        self.create_appointment(service=self.rival_service)
        self.client.force_authenticate(self.owner)

        response = self.client.get(self.url)

        self.assertEqual(response.data["count"], 0)

    def test_owner_who_is_also_a_client_booking_elsewhere_sees_only_owned_business_appointments(self):
        # Role decides the scope: an owner never sees appointments merely because they are the client on them.
        Appointment.objects.create(service=self.rival_service, client=self.owner, start_time=self.future())
        self.client.force_authenticate(self.owner)

        self.assertEqual(self.client.get(self.url).data["count"], 0)

    def test_results_are_ordered_by_start_time(self):
        later = self.create_appointment(days=3)
        earlier = self.create_appointment(days=1)
        middle = self.create_appointment(days=2)

        response = self.client.get(self.url)

        self.assertEqual(self.ids(response), [earlier.pk, middle.pk, later.pk])

    def test_pagination_and_page_size(self):
        for slot in range(25):
            self.create_appointment(minutes=30 * slot)

        first_page = self.client.get(self.url)
        second_page = self.client.get(self.url, {"page": 2, "page_size": 10})

        self.assertEqual(first_page.data["count"], 25)
        self.assertEqual(len(first_page.data["results"]), 20)
        self.assertEqual(len(second_page.data["results"]), 10)
        self.assertIn("page_size=10", second_page.data["next"])

    def test_from_and_to_filter_on_start_time_inclusively(self):
        early = self.create_appointment(days=1)
        middle = self.create_appointment(days=3)
        late = self.create_appointment(days=5)

        both = self.client.get(self.url, {"from": self.iso(early.start_time), "to": self.iso(middle.start_time)})
        only_from = self.client.get(self.url, {"from": self.iso(middle.start_time)})
        only_to = self.client.get(self.url, {"to": self.iso(middle.start_time)})

        self.assertEqual(self.ids(both), [early.pk, middle.pk])
        self.assertEqual(self.ids(only_from), [middle.pk, late.pk])
        self.assertEqual(self.ids(only_to), [early.pk, middle.pk])

    def test_status_filter_accepts_repeated_values(self):
        pending = self.create_appointment(days=1, status=AppointmentStatus.Pending)
        confirmed = self.create_appointment(days=2, status=AppointmentStatus.Confirmed)
        self.create_appointment(days=3, status=AppointmentStatus.Cancelled)

        single = self.client.get(self.url, {"status": "confirmed"})
        several = self.client.get(self.url + "?status=pending&status=confirmed")

        self.assertEqual(self.ids(single), [confirmed.pk])
        self.assertEqual(self.ids(several), [pending.pk, confirmed.pk])

    def test_cancelled_appointments_are_listed_by_default(self):
        cancelled = self.create_appointment(status=AppointmentStatus.Cancelled)

        self.assertEqual(self.ids(self.client.get(self.url)), [cancelled.pk])

    def test_filters_are_preserved_in_pagination_links(self):
        for slot in range(3):
            self.create_appointment(minutes=30 * slot, status=AppointmentStatus.Confirmed)

        response = self.client.get(self.url + "?status=confirmed&page_size=2")

        self.assertIn("status=confirmed", response.data["next"])

    def test_invalid_status_returns_400(self):
        response = self.client.get(self.url, {"status": "done"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)

    def test_capitalized_status_returns_400(self):
        response = self.client.get(self.url, {"status": "Confirmed"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)

    def test_naive_from_returns_400(self):
        response = self.client.get(self.url, {"from": "2099-01-01T10:00:00"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("from", response.data)

    def test_from_after_to_returns_400_on_to(self):
        response = self.client.get(
            self.url, {"from": self.iso(self.future(3)), "to": self.iso(self.future(1))}
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("to", response.data)

    def test_query_count_does_not_grow_with_appointments(self):
        self.create_appointment()
        with CaptureQueriesContext(connection) as one_appointment:
            self.client.get(self.url)

        for slot in range(1, 10):
            self.create_appointment(minutes=30 * slot, service=self.rival_service if slot % 2 else None)
        with CaptureQueriesContext(connection) as ten_appointments:
            response = self.client.get(self.url)

        self.assertEqual(len(response.data["results"]), 10)
        self.assertEqual(len(ten_appointments), len(one_appointment))

    def test_query_does_not_fetch_client_credentials(self):
        self.create_appointment()

        with CaptureQueriesContext(connection) as queries:
            self.client.get(self.url)

        # The pagination COUNT query runs first and selects no columns, so look at the row query specifically.
        appointment_query = next(
            q["sql"] for q in queries if '"business_appointment"' in q["sql"] and "COUNT(" not in q["sql"]
        )
        self.assertIn('"full_name"', appointment_query)
        self.assertNotIn("password", appointment_query)
        self.assertNotIn('"email"', appointment_query)


class BusinessSummaryFixtureMixin(AppointmentFixtureMixin):
    def create_appointment(self, service, client, *, days=1, minutes=0, status=AppointmentStatus.Pending):
        return Appointment.objects.create(
            service=service, client=client, start_time=self.future(days, minutes=minutes), status=status
        )

    def add_service(self, business, *, name, price="50.00"):
        return Service.objects.create(business=business, name=name, duration_minutes=30, price=Decimal(price))


class BusinessSummaryServiceTests(BusinessSummaryFixtureMixin, TestCase):
    def setUp(self):
        self.owner = self.create_user("owner@example.com", Role.BusinessOwner)
        self.client_user = self.create_user("client@example.com", Role.Client)
        self.service = self.create_service(self.owner, price="80.00")
        self.business = self.service.business
        self.summaries = BusinessSummaryService()

    def summarize(self, summaries=None, owner=None):
        return list(
            (summaries or self.summaries).summarize(request_owner=owner or self.owner, business=self.business)
        )

    def test_counts_future_active_appointments_and_multiplies_by_price(self):
        self.create_appointment(self.service, self.client_user, days=1)
        self.create_appointment(self.service, self.client_user, days=2, status=AppointmentStatus.Confirmed)

        (item,) = self.summarize()

        self.assertEqual(item.pk, self.service.pk)
        self.assertEqual(item.appointment_count, 2)
        self.assertEqual(item.expected_revenue, Decimal("160.00"))

    def test_cancelled_appointments_are_excluded(self):
        self.create_appointment(self.service, self.client_user, days=1)
        self.create_appointment(self.service, self.client_user, days=2, status=AppointmentStatus.Cancelled)

        (item,) = self.summarize()

        self.assertEqual(item.appointment_count, 1)
        self.assertEqual(item.expected_revenue, Decimal("80.00"))

    def test_past_appointments_are_excluded(self):
        self.create_appointment(self.service, self.client_user, days=-1)
        self.create_appointment(self.service, self.client_user, days=1)

        (item,) = self.summarize()

        self.assertEqual(item.appointment_count, 1)

    def test_appointment_starting_exactly_now_is_not_future(self):
        fixed_now = self.future()
        Appointment.objects.create(service=self.service, client=self.client_user, start_time=fixed_now)
        Appointment.objects.create(
            service=self.service, client=self.client_user, start_time=fixed_now + timedelta(minutes=30)
        )

        (item,) = self.summarize(BusinessSummaryService(now=lambda: fixed_now))

        self.assertEqual(item.appointment_count, 1)

    def test_service_without_appointments_reports_zero(self):
        (item,) = self.summarize()

        self.assertEqual(item.appointment_count, 0)
        self.assertEqual(item.expected_revenue, Decimal("0.00"))

    def test_services_are_ordered_by_id_and_scoped_to_the_business(self):
        second = self.add_service(self.business, name="Beard trim", price="40.00")
        self.create_service(self.owner, name="Elsewhere", business_name="Other Shop")

        self.assertEqual([item.pk for item in self.summarize()], [self.service.pk, second.pk])

    def test_appointments_of_other_services_are_not_counted(self):
        second = self.add_service(self.business, name="Beard trim", price="40.00")
        self.create_appointment(second, self.client_user, days=1)
        self.create_appointment(second, self.client_user, days=2)

        first_item, second_item = self.summarize()

        self.assertEqual((first_item.appointment_count, first_item.expected_revenue), (0, Decimal("0.00")))
        self.assertEqual((second_item.appointment_count, second_item.expected_revenue), (2, Decimal("80.00")))

    def test_non_owner_raises_business_not_owned(self):
        rival = self.create_user("rival@example.com", Role.BusinessOwner)

        with self.assertRaises(BusinessNotOwnedError):
            self.summarize(owner=rival)

    def test_superuser_has_no_ownership_bypass(self):
        admin = User.objects.create_superuser(
            email="admin@example.com", password="S3cure-pass!", full_name="Admin", role=Role.BusinessOwner
        )

        with self.assertRaises(BusinessNotOwnedError):
            self.summarize(owner=admin)


class BusinessSummaryApiTests(BusinessSummaryFixtureMixin, APITestCase):
    def setUp(self):
        self.owner = self.create_user("owner@example.com", Role.BusinessOwner)
        self.rival_owner = self.create_user("rival@example.com", Role.BusinessOwner)
        self.client_user = self.create_user("client@example.com", Role.Client)
        self.service = self.create_service(self.owner, price="80.00")
        self.business = self.service.business
        self.url = self.url_for(self.business.pk)
        self.client.force_authenticate(self.owner)

    @staticmethod
    def url_for(business_id):
        return reverse("business-summary", args=[business_id])

    def test_requires_authentication(self):
        self.client.force_authenticate(None)

        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_client_gets_403(self):
        self.client.force_authenticate(self.client_user)

        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_403_FORBIDDEN)

    def test_client_gets_403_even_for_an_unknown_business(self):
        self.client.force_authenticate(self.client_user)

        self.assertEqual(self.client.get(self.url_for(999999)).status_code, status.HTTP_403_FORBIDDEN)

    def test_role_is_checked_against_the_database_not_the_token_claim(self):
        token = AccessToken.for_user(self.owner)
        token["role"] = "BusinessOwner"
        User.objects.filter(pk=self.owner.pk).update(role=Role.Client)
        self.client.force_authenticate(None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_403_FORBIDDEN)

    def test_another_owner_gets_403(self):
        self.client.force_authenticate(self.rival_owner)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertNotIn("results", response.data)

    def test_superuser_who_does_not_own_the_business_gets_403(self):
        admin = User.objects.create_superuser(
            email="admin@example.com", password="S3cure-pass!", full_name="Admin", role=Role.BusinessOwner
        )
        self.client.force_authenticate(admin)

        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_403_FORBIDDEN)

    def test_unknown_business_returns_404_for_an_owner(self):
        self.assertEqual(self.client.get(self.url_for(999999)).status_code, status.HTTP_404_NOT_FOUND)

    def test_owner_gets_paginated_envelope_with_one_item_per_service(self):
        busy = self.add_service(self.business, name="Beard trim", price="40.00")
        self.create_appointment(busy, self.client_user, days=1)
        self.create_appointment(busy, self.client_user, days=2, status=AppointmentStatus.Confirmed)
        self.create_appointment(busy, self.client_user, days=3, status=AppointmentStatus.Cancelled)
        self.create_appointment(busy, self.client_user, days=-1)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data), {"count", "next", "previous", "results"})
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(
            response.data["results"],
            [
                {"service_id": self.service.pk, "name": "Haircut", "appointment_count": 0, "expected_revenue": "0.00"},
                {"service_id": busy.pk, "name": "Beard trim", "appointment_count": 2, "expected_revenue": "80.00"},
            ],
        )

    def test_does_not_include_other_businesses_or_owners_data(self):
        rival_service = self.create_service(self.rival_owner, business_name="Rival Cuts")
        self.create_appointment(rival_service, self.client_user, days=1)

        response = self.client.get(self.url)

        self.assertEqual([item["service_id"] for item in response.data["results"]], [self.service.pk])
        self.assertEqual(response.data["results"][0]["appointment_count"], 0)

    def test_pagination_and_page_size(self):
        for index in range(24):
            self.add_service(self.business, name=f"Extra {index}")

        first_page = self.client.get(self.url)
        second_page = self.client.get(self.url, {"page": 2, "page_size": 10})

        self.assertEqual(first_page.data["count"], 25)
        self.assertEqual(len(first_page.data["results"]), 20)
        self.assertEqual(len(second_page.data["results"]), 10)
        self.assertIn("page_size=10", second_page.data["next"])

    def test_query_count_does_not_grow_with_services_or_appointments(self):
        self.create_appointment(self.service, self.client_user, days=1)
        with CaptureQueriesContext(connection) as one_service:
            self.client.get(self.url)

        for index in range(9):
            extra = self.add_service(self.business, name=f"Extra {index}")
            for slot in range(3):
                self.create_appointment(extra, self.client_user, days=1, minutes=30 * slot)
        with CaptureQueriesContext(connection) as ten_services:
            response = self.client.get(self.url)

        self.assertEqual(len(response.data["results"]), 10)
        self.assertEqual(len(ten_services), len(one_service))

    def test_query_does_not_fetch_credentials(self):
        self.create_appointment(self.service, self.client_user, days=1)

        with CaptureQueriesContext(connection) as queries:
            self.client.get(self.url)

        self.assertFalse(any("password" in q["sql"] for q in queries))


class AppointmentAdminTests(AppointmentFixtureMixin, TestCase):
    def setUp(self):
        self.owner = self.create_user("owner@example.com", Role.BusinessOwner)
        self.admin = User.objects.create_superuser(
            email="admin@example.com", password="S3cure-pass!", full_name="Admin", role=Role.BusinessOwner
        )
        self.client.force_login(self.admin)

    def test_add_form_query_count_does_not_grow_with_services(self):
        self.create_service(self.owner)
        self.client.get(reverse("admin:business_appointment_add"))  # warm one-time caches (content types)
        with CaptureQueriesContext(connection) as one_service:
            response = self.client.get(reverse("admin:business_appointment_add"))
        self.assertEqual(response.status_code, 200)

        for index in range(10):
            self.create_service(self.owner, name=f"Service {index}", business_name=f"Business {index}")
        with CaptureQueriesContext(connection) as eleven_services:
            self.client.get(reverse("admin:business_appointment_add"))

        self.assertEqual(len(eleven_services), len(one_service))

    def test_service_autocomplete_query_count_does_not_grow_with_results(self):
        params = {"app_label": "business", "model_name": "appointment", "field_name": "service", "term": ""}
        self.create_service(self.owner)
        with CaptureQueriesContext(connection) as one_result:
            response = self.client.get(reverse("admin:autocomplete"), params)
        self.assertEqual(len(response.json()["results"]), 1)

        for index in range(10):
            self.create_service(self.owner, name=f"Service {index}", business_name=f"Business {index}")
        with CaptureQueriesContext(connection) as eleven_results:
            response = self.client.get(reverse("admin:autocomplete"), params)

        self.assertEqual(len(response.json()["results"]), 11)
        self.assertEqual(len(eleven_results), len(one_result))

    def create_appointment(self, index):
        service = self.create_service(self.owner, name=f"Service {index}", business_name=f"Business {index}")
        client = self.create_user(f"client{index}@example.com", Role.Client)
        start = self.future(days=index + 1)
        return Appointment.objects.create(
            service=service, client=client, start_time=start, end_time=start + timedelta(minutes=30)
        )

    def test_business_changelist_query_count_does_not_grow_with_rows(self):
        Business.objects.create(name="Business 0", owner=self.owner, category=Category.Barbers)
        self.client.get(reverse("admin:business_business_changelist"))  # warm one-time caches (content types)
        with CaptureQueriesContext(connection) as one_row:
            response = self.client.get(reverse("admin:business_business_changelist"))
        self.assertEqual(response.status_code, 200)

        for index in range(1, 11):
            owner = self.create_user(f"owner{index}@example.com", Role.BusinessOwner)
            Business.objects.create(name=f"Business {index}", owner=owner, category=Category.Barbers)
        with CaptureQueriesContext(connection) as eleven_rows:
            self.client.get(reverse("admin:business_business_changelist"))

        self.assertEqual(len(eleven_rows), len(one_row))

    def test_appointment_changelist_query_count_does_not_grow_with_rows(self):
        self.create_appointment(0)
        self.client.get(reverse("admin:business_appointment_changelist"))  # warm one-time caches (content types)
        with CaptureQueriesContext(connection) as one_row:
            response = self.client.get(reverse("admin:business_appointment_changelist"))
        self.assertEqual(response.status_code, 200)

        for index in range(1, 11):
            self.create_appointment(index)
        with CaptureQueriesContext(connection) as eleven_rows:
            self.client.get(reverse("admin:business_appointment_changelist"))

        self.assertEqual(len(eleven_rows), len(one_row))


class SeedDataCommandTests(TestCase):
    @override_settings(DEBUG=False)
    def test_refuses_to_run_without_debug(self):
        owner = User.objects.create_user(
            email="owner@bookit.test", password="S3cure-pass!", full_name="Owner", role=Role.BusinessOwner
        )

        with self.assertRaises(CommandError):
            call_command("seed_data", stdout=StringIO())

        self.assertTrue(User.objects.filter(pk=owner.pk).exists())
