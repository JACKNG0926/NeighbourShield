from rest_framework.permissions import BasePermission


class IsTownshipAdmin(BasePermission):
    """Allow superusers and the application's township administrators."""

    message = 'Township administrator access is required.'

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_township_admin)
