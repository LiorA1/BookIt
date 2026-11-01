from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Role
from .services import UserService


class RegisterRequestSerializer(serializers.ModelSerializer):
    role = serializers.ChoiceField(choices=Role.names)

    class Meta:
        model = get_user_model()
        fields = ["email", "password", "full_name", "role"]
        extra_kwargs = {
            "password": {"write_only": True, "trim_whitespace": False, "style": {"input_type": "password"}},
            # Uniqueness is checked case-insensitively in validate_email instead of the default UniqueValidator.
            "email": {"validators": []},
        }

    def __init__(self, *args, user_service: UserService, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service

    def validate_email(self, value):
        value = get_user_model().objects.normalize_email(value)
        if self.user_service.email_exists(value):
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_role(self, value):
        return Role[value]

    def validate(self, attrs):
        candidate = get_user_model()(email=attrs["email"], full_name=attrs["full_name"])
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})
        return attrs


class LoginRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False, style={"input_type": "password"})


class TokenResponseSerializer(serializers.Serializer):
    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True)


class UserResponseSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = get_user_model()
        fields = ["id", "email", "full_name", "role"]
        read_only_fields = fields

    def get_role(self, user):
        return Role(user.role).name
