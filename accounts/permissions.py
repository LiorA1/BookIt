from rest_framework.permissions import BasePermission

from .models import Role


class IsClient(BasePermission):
    """Allows only authenticated users whose current database role is Client.

    request.user is loaded from the database on every request, so a stale JWT role claim cannot grant access.
    """

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == Role.Client)
