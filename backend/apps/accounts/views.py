"""Views for Authentication and Profile management."""

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated

from apps.accounts.serializers import (
    RegisterSerializer,
    EmailOrMobileLoginSerializer,
    ProfileSerializer,
    ProfileUpdateSerializer,
)


class RegisterView(APIView):
    """Public user registration endpoint."""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(
                ProfileSerializer(user, context={'request': request}).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    """JWT Login endpoint accepting Email OR Mobile + Password (NEVER username)."""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = EmailOrMobileLoginSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            return Response(serializer.validated_data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_401_UNAUTHORIZED)


class ProfileMeView(APIView):
    """User profile management strictly scoped to the JWT token's user (request.user).

    MENTOR SPEC:
    - Must scope to user_id decoded from JWT access token, NEVER a parameter.
    - Locked fields: gated_society_id, group_id.
    - Never editable: date_joined, is_staff, is_active, is_superuser.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = ProfileSerializer(request.user, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        serializer = ProfileUpdateSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={'request': request},
        )
        if serializer.is_valid():
            user = serializer.save()
            return Response(
                ProfileSerializer(user, context={'request': request}).data,
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request):
        user = request.user
        user.is_active = False
        user.save()
        return Response(
            {"message": "User profile has been successfully deactivated."},
            status=status.HTTP_200_OK,
        )
