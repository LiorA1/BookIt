from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _


class Role(models.IntegerChoices):
    Client = 0
    BusinessOwner = 1


class CustomUserManager(BaseUserManager):
    """Manager for a user model that uses email as the login identifier."""

    use_in_migrations = True

    def normalize_email(self, email):
        return super().normalize_email(email).lower()

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("The email must be set")
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class CustomUser(AbstractUser):
    """CustomUser Model"""

    username = None
    first_name = None
    last_name = None

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name", "role"]

    email = models.EmailField(_("email address"), unique=True)
    full_name = models.CharField(_("full name"), max_length=150)
    role = models.IntegerField(choices=Role.choices)

    objects = CustomUserManager()

    class Meta(AbstractUser.Meta):
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                name="accounts_customuser_email_ci_unique",
                violation_error_message=_("A user with this email already exists."),
            ),
        ]

    def save(self, *args, **kwargs):
        # Login looks emails up lowercased, so every write path (admin forms, direct ORM) must store them that way.
        self.email = type(self).objects.normalize_email(self.email)
        super().save(*args, **kwargs)

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.full_name

    def __str__(self):
        return self.email
