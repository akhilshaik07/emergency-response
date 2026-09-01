"""Role-based permission classes matching mentor assignment requirements."""

from rest_framework import permissions


class IsAdminUserRole(permissions.BasePermission):
    """Permission granting access only to Super Admin (1) or Admin (2)."""

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            (request.user.group_id in [1, 2] or request.user.is_superuser)
        )


class IsSubAdminUserRole(permissions.BasePermission):
    """Permission granting access to Sub Admin (3)."""

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.group_id == 3
        )


class IsVolunteerRole(permissions.BasePermission):
    """Permission granting access to Volunteer (4)."""

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.group_id == 4
        )


class IsGuardianRole(permissions.BasePermission):
    """Permission granting access to Guardian (5)."""

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.group_id == 5
        )
