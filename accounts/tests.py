import io
from contextlib import redirect_stdout

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from .exceptions import EmailAlreadyRegisteredError, InvalidCredentialsError
from .models import Role
from .services import AuthService, UserService

User = get_user_model()


class CustomUserModelTests(TestCase):
    def test_save_normalizes_email_outside_the_manager(self):
        user = User(email="Dana@Example.COM", full_name="Dana", role=Role.Client)
        user.set_password("S3cure-pass!")
        user.save()

        user.refresh_from_db()
        self.assertEqual(user.email, "dana@example.com")
        tokens = AuthService(user_model=User).login(email="Dana@Example.COM", password="S3cure-pass!")
        self.assertEqual(str(AccessToken(tokens["access"])["user_id"]), str(user.pk))

    def test_database_rejects_case_variant_duplicate_email(self):
        User.objects.create_user(email="dana@example.com", password="S3cure-pass!", full_name="Dana", role=Role.Client)
        other = User.objects.create_user(
            email="other@example.com", password="S3cure-pass!", full_name="Other", role=Role.Client
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            # update() bypasses save(), so only the database constraint can stop the duplicate.
            User.objects.filter(pk=other.pk).update(email="DANA@example.com")

    def test_model_validation_rejects_case_variant_duplicate_email(self):
        User.objects.create_user(email="dana@example.com", password="S3cure-pass!", full_name="Dana", role=Role.Client)
        candidate = User(email="DANA@example.com", full_name="Other", role=Role.Client)

        with self.assertRaises(ValidationError):
            candidate.validate_constraints()


class UserServiceTests(TestCase):
    def setUp(self):
        self.service = UserService(user_model=User)

    def test_register_creates_user_with_hashed_password(self):
        user = self.service.register(
            email="Dana@Example.com", password="S3cure-pass!", full_name="Dana Levi", role=Role.Client
        )

        self.assertEqual(user.email, "dana@example.com")
        self.assertEqual(user.full_name, "Dana Levi")
        self.assertEqual(user.role, Role.Client)
        self.assertNotEqual(user.password, "S3cure-pass!")
        self.assertTrue(user.check_password("S3cure-pass!"))

    def test_register_duplicate_email_raises(self):
        self.service.register(email="dana@example.com", password="S3cure-pass!", full_name="Dana", role=Role.Client)

        with self.assertRaises(EmailAlreadyRegisteredError):
            self.service.register(
                email="DANA@example.com", password="S3cure-pass!", full_name="Other", role=Role.BusinessOwner
            )


class RegisterApiTests(APITestCase):
    url = reverse("register")

    def payload(self, **overrides):
        data = {
            "email": "owner@example.com",
            "password": "S3cure-pass!",
            "full_name": "Yossi Cohen",
            "role": "BusinessOwner",
        }
        data.update(overrides)
        return data

    def test_register_success(self):
        response = self.client.post(self.url, self.payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            set(response.data), {"id", "email", "full_name", "role"}
        )
        self.assertEqual(response.data["role"], "BusinessOwner")
        user = User.objects.get(pk=response.data["id"])
        self.assertEqual(user.role, Role.BusinessOwner)
        self.assertTrue(user.check_password("S3cure-pass!"))

    def test_register_duplicate_email(self):
        self.client.post(self.url, self.payload(), format="json")

        response = self.client.post(self.url, self.payload(email="OWNER@example.com"), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)
        self.assertEqual(User.objects.count(), 1)

    def test_register_missing_fields(self):
        response = self.client.post(self.url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(set(response.data), {"email", "password", "full_name", "role"})

    def test_register_invalid_role(self):
        response = self.client.post(self.url, self.payload(role="Admin"), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("role", response.data)

    def test_register_invalid_email(self):
        response = self.client.post(self.url, self.payload(email="not-an-email"), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_register_weak_password(self):
        response = self.client.post(self.url, self.payload(password="123"), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)
        self.assertEqual(User.objects.count(), 0)


class AuthServiceTests(TestCase):
    def setUp(self):
        self.service = AuthService(user_model=User)
        self.user = User.objects.create_user(
            email="owner@example.com", password="S3cure-pass!", full_name="Yossi", role=Role.BusinessOwner
        )

    def test_login_returns_tokens_with_user_id_and_role_claims(self):
        tokens = self.service.login(email="Owner@Example.com", password="S3cure-pass!")

        access = AccessToken(tokens["access"])
        refresh = RefreshToken(tokens["refresh"])
        self.assertEqual(str(access["user_id"]), str(self.user.pk))
        self.assertEqual(access["role"], "BusinessOwner")
        self.assertEqual(str(refresh["user_id"]), str(self.user.pk))

    def test_issue_tokens_writes_nothing_to_stdout(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            tokens = self.service.issue_tokens(self.user)

        self.assertEqual(stdout.getvalue(), "")
        self.assertTrue(tokens["access"])
        self.assertTrue(tokens["refresh"])

    def test_login_wrong_password_raises(self):
        with self.assertRaises(InvalidCredentialsError):
            self.service.login(email="owner@example.com", password="wrong-pass")

    def test_login_unknown_email_raises(self):
        with self.assertRaises(InvalidCredentialsError):
            self.service.login(email="nobody@example.com", password="S3cure-pass!")

    def test_login_inactive_user_raises(self):
        self.user.is_active = False
        self.user.save()

        with self.assertRaises(InvalidCredentialsError):
            self.service.login(email="owner@example.com", password="S3cure-pass!")


class LoginApiTests(APITestCase):
    url = reverse("login")

    def setUp(self):
        self.user = User.objects.create_user(
            email="client@example.com", password="S3cure-pass!", full_name="Dana", role=Role.Client
        )

    def test_login_success(self):
        response = self.client.post(
            self.url, {"email": "client@example.com", "password": "S3cure-pass!"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data), {"access", "refresh"})
        self.assertEqual(AccessToken(response.data["access"])["role"], "Client")

    def test_login_invalid_credentials(self):
        response = self.client.post(
            self.url, {"email": "client@example.com", "password": "wrong-pass"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn("access", response.data)
        self.assertEqual(response["WWW-Authenticate"], 'Bearer realm="api"')

    def test_login_missing_fields(self):
        response = self.client.post(self.url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(set(response.data), {"email", "password"})
