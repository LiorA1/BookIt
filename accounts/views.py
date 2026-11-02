from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from .exceptions import EmailAlreadyRegisteredError, InvalidCredentialsError
from .serializers import (
    LoginRequestSerializer,
    RegisterRequestSerializer,
    TokenResponseSerializer,
    UserResponseSerializer,
)
from .services import AuthService, UserService


class RegisterView(APIView):
    """POST /api/auth/register - creates a user (email, password, full name, role)."""

    authentication_classes = []
    permission_classes = [AllowAny]
    user_service_class = UserService

    def post(self, request):
        user_service = self.user_service_class()
        serializer = RegisterRequestSerializer(data=request.data, user_service=user_service)
        serializer.is_valid(raise_exception=True)

        try:
            user = user_service.register(**serializer.validated_data)
        except EmailAlreadyRegisteredError:
            return Response(
                {"email": ["A user with this email already exists."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(UserResponseSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    """POST /api/auth/login - validates credentials and returns access and refresh JWTs."""
    # {"email": "my@do.com", "password": "tlv08v!!!", "full_name": "Lior A", "role": "Client"}
    authentication_classes = []
    permission_classes = [AllowAny]
    auth_service_class = AuthService

    def post(self, request):
        serializer = LoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            tokens = self.auth_service_class().login(request=request, **serializer.validated_data)
        except InvalidCredentialsError:
            # Returned directly: DRF downgrades AuthenticationFailed to 403 on views without authenticators.
            return Response(
                {"detail": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED,
                headers={"WWW-Authenticate": JWTAuthentication().authenticate_header(request)},
            )

        return Response(TokenResponseSerializer(tokens).data, status=status.HTTP_200_OK)
