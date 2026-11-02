import os
import random
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import Role
from business.models import Appointment, Business, Category, Service

SEED_EMAIL_DOMAIN = "bookit.test"
DEFAULT_SEED_PASSWORD = "BookIt-Demo-2026!"
RANDOM_SEED = 2026

BUSINESS_TIME_ZONE = ZoneInfo("Asia/Jerusalem")
OPENING_TIME = time(9, 0)
SLOTS_PER_DAY = 18
SLOT_MINUTES = 30
DAYS_AROUND_TODAY = 30
APPOINTMENT_COUNT = 200

OWNER_NAMES = ["Yossi Cohen", "Dana Levi", "Avi Mizrahi", "Noa Peretz", "Eitan Biton"]
CLIENT_NAMES = [
    "Maya Friedman", "Omer Shapiro", "Tamar Katz", "Itay Azulay", "Shira Dahan",
    "Ron Avraham", "Yael Ben-David", "Guy Ohana", "Lior Malka", "Noam Golan",
]
BARBER_NAMES = [
    "Sharp Fade", "Clean Cut Studio", "The Barber Room", "Razor Edge", "Gentlemen's Corner",
    "Old Town Barbers", "Fresh Look", "Blade & Comb", "Classic Cuts", "Urban Barber",
]
TUTOR_NAMES = [
    "Math Masters", "Bagrut Boost", "English Hub", "Physics Lab", "Code Mentors",
    "Smart Study", "Grammar Garage", "Exam Ready", "Science Space", "Learning Loft",
]
SERVICE_CATALOG = {
    Category.Barbers: [
        ("Haircut", Decimal("80.00")),
        ("Beard trim", Decimal("50.00")),
        ("Kids haircut", Decimal("60.00")),
        ("Hair wash and style", Decimal("70.00")),
        ("Hot towel shave", Decimal("90.00")),
    ],
    Category.Tutors: [
        ("Math lesson", Decimal("150.00")),
        ("English lesson", Decimal("140.00")),
        ("Physics lesson", Decimal("160.00")),
        ("Bagrut exam prep", Decimal("180.00")),
        ("Programming lesson", Decimal("200.00")),
    ],
}


class Command(BaseCommand):
    help = (
        f"Replace all @{SEED_EMAIL_DOMAIN} users and their data with a deterministic demo data set. "
        "Seeded users share the SEED_PASSWORD environment value or the documented default."
    )

    def handle(self, *args, **options):
        rng = random.Random(RANDOM_SEED)
        password_hash = make_password(os.environ.get("SEED_PASSWORD") or DEFAULT_SEED_PASSWORD)

        with transaction.atomic():
            User = get_user_model()
            User.objects.filter(email__iendswith=f"@{SEED_EMAIL_DOMAIN}").delete()

            owners, clients = self._create_users(User, password_hash)
            businesses = self._create_businesses(owners)
            services = self._create_services(businesses)
            appointments = self._create_appointments(rng, services, clients)

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {len(owners)} owners, {len(clients)} clients, 1 admin, {len(businesses)} businesses, "
            f"{len(services)} services, and {len(appointments)} appointments."
        ))

    def _create_users(self, User, password_hash):
        def build(name, email, role, **extra):
            return User(email=email, full_name=name, role=role, password=password_hash, **extra)

        owners = [
            build(name, f"owner{index}@{SEED_EMAIL_DOMAIN}", Role.BusinessOwner)
            for index, name in enumerate(OWNER_NAMES, start=1)
        ]
        clients = [
            build(name, f"client{index}@{SEED_EMAIL_DOMAIN}", Role.Client)
            for index, name in enumerate(CLIENT_NAMES, start=1)
        ]
        admin = build(
            "BookIt Admin", f"admin@{SEED_EMAIL_DOMAIN}", Role.BusinessOwner, is_staff=True, is_superuser=True,
        )
        User.objects.bulk_create([*owners, *clients, admin])
        return owners, clients

    def _create_businesses(self, owners):
        businesses = []
        for owner_index, owner in enumerate(owners):
            for category, names in ((Category.Barbers, BARBER_NAMES), (Category.Tutors, TUTOR_NAMES)):
                for name in names[owner_index * 2:owner_index * 2 + 2]:
                    businesses.append(Business(name=name, owner=owner, category=category))
        return Business.objects.bulk_create(businesses)

    def _create_services(self, businesses):
        services = []
        for business_index, business in enumerate(businesses):
            catalog = SERVICE_CATALOG[Category(business.category)]
            service_count = 3 if business_index % 2 == 0 else 2
            for offset in range(service_count):
                name, price = catalog[(business_index + offset) % len(catalog)]
                services.append(Service(business=business, name=name, duration_minutes=SLOT_MINUTES, price=price))
        return Service.objects.bulk_create(services)

    def _create_appointments(self, rng, services, clients):
        now = timezone.now()
        today = timezone.localtime(now, BUSINESS_TIME_ZONE).date()
        booked_service_slots = set()
        booked_client_slots = set()
        appointments = []

        while len(appointments) < APPOINTMENT_COUNT:
            day = today + timedelta(days=rng.randint(-DAYS_AROUND_TODAY, DAYS_AROUND_TODAY))
            opening = datetime.combine(day, OPENING_TIME, tzinfo=BUSINESS_TIME_ZONE)
            start_time = opening + timedelta(minutes=SLOT_MINUTES * rng.randrange(SLOTS_PER_DAY))
            service = rng.choice(services)
            client = rng.choice(clients)
            status = self._pick_status(rng, is_past=start_time < now)

            service_slot = (service.pk, start_time)
            client_slot = (client.pk, start_time)
            if service_slot in booked_service_slots or client_slot in booked_client_slots:
                continue
            booked_service_slots.add(service_slot)
            booked_client_slots.add(client_slot)
            appointments.append(Appointment(service=service, client=client, start_time=start_time, status=status))

        return Appointment.objects.bulk_create(appointments)

    @staticmethod
    def _pick_status(rng, *, is_past):
        Status = Appointment.AppointmentStatus
        if is_past:
            return rng.choices([Status.Confirmed, Status.Cancelled], weights=[85, 15])[0]
        return rng.choices([Status.Pending, Status.Confirmed, Status.Cancelled], weights=[45, 40, 15])[0]
