from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError, transaction
from rest_framework_simplejwt.tokens import RefreshToken

from .exceptions import EmailAlreadyRegisteredError, InvalidCredentialsError
from .models import Role


class UserService:
    def __init__(self, user_model=None):
        self.user_model = user_model or get_user_model()

    def email_exists(self, email: str) -> bool:
        return self.user_model.objects.filter(email__iexact=email).exists()

    def register(self, *, email: str, password: str, full_name: str, role: Role):
        try:
            with transaction.atomic():
                return self.user_model.objects.create_user(
                    email=email,
                    password=password,
                    full_name=full_name,
                    role=role,
                )
        except IntegrityError as exc:
            # The unique constraint is the source of truth when two requests race past validation.
            raise EmailAlreadyRegisteredError(email) from exc


class AuthService:
    def __init__(self, user_model=None, authenticate_func=authenticate, token_class=RefreshToken):
        self.user_model = user_model or get_user_model()
        self.authenticate = authenticate_func
        self.token_class = token_class

    def login(self, *, email: str, password: str, request=None) -> dict:
        # Emails are stored lowercased and the auth backend looks them up with an exact match.
        normalized_email = self.user_model.objects.normalize_email(email)
        user = self.authenticate(request, email=normalized_email, password=password)
        if user is None:
            raise InvalidCredentialsError()
        return self.issue_tokens(user)

    def issue_tokens(self, user) -> dict:
        refresh = self.token_class.for_user(user)
        print(f"refresh: {refresh}")
        print(f"type of refresh: {type(refresh)}")
        refresh["role"] = Role(user.role).name
        return {"access": str(refresh.access_token), "refresh": str(refresh)}
