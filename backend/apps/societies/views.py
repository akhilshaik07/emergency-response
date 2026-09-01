"""Views for GatedSociety CRUD with role-based filtering and WHERE-condition scoping."""

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, NotFound
from django.shortcuts import get_object_or_404

from apps.societies.models import GatedSociety
from apps.societies.serializers import GatedSocietySerializer
from apps.accounts.permissions import IsAdminUserRole


class GatedSocietyListCreateView(APIView):
    """List societies (Admin sees all, others see only their own) & Create (Admin only)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """MENTOR SPEC: Admin sees all societies; every other role sees only their own."""
        user = request.user
        if user.group_id in [1, 2] or user.is_superuser:
            # Super Admin & Admin see all
            societies = GatedSociety.objects.all()
        else:
            # Sub Admin, Volunteer, Guardian see ONLY their own society
            if user.gated_society_id:
                societies = GatedSociety.objects.filter(id=user.gated_society_id)
            else:
                societies = GatedSociety.objects.none()

        serializer = GatedSocietySerializer(societies, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        """MENTOR SPEC: Admin only can create a gated society."""
        if not (request.user.group_id in [1, 2] or request.user.is_superuser):
            raise PermissionDenied("Only Admin or Super Admin can create a gated society.")

        serializer = GatedSocietySerializer(data=request.data)
        if serializer.is_valid():
            society = serializer.save()
            return Response(GatedSocietySerializer(society).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GatedSocietyDetailView(APIView):
    """Retrieve, Update, and Delete a specific Gated Society using explicit WHERE condition on ID."""
    permission_classes = [IsAuthenticated]

    def _get_society(self, pk):
        """Fetch society with strict WHERE condition on specific ID."""
        return get_object_or_404(GatedSociety, id=pk)

    def _check_access(self, user, society, require_edit=False):
        """Enforce role permissions: Admin has global access; Sub Admin has access to own society."""
        is_admin = (user.group_id in [1, 2] or user.is_superuser)
        if is_admin:
            return True

        # Non-admin viewing
        if not require_edit:
            if user.gated_society_id == society.id:
                return True
            raise PermissionDenied("You do not have permission to view this society.")

        # Sub Admin editing/deleting own society
        is_sub_admin = (user.group_id == 3 and (user.gated_society_id == society.id or society.sub_admin_id == user.id))
        if is_sub_admin:
            return True

        raise PermissionDenied("You do not have permission to modify or delete this society.")

    def get(self, request, pk):
        society = self._get_society(pk)
        self._check_access(request.user, society, require_edit=False)
        return Response(GatedSocietySerializer(society).data, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        society = self._get_society(pk)
        self._check_access(request.user, society, require_edit=True)
        serializer = GatedSocietySerializer(society, data=request.data, partial=True)
        if serializer.is_valid():
            updated = serializer.save()
            return Response(GatedSocietySerializer(updated).data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        return self.patch(request, pk)

    def delete(self, request, pk):
        society = self._get_society(pk)
        self._check_access(request.user, society, require_edit=True)
        society_name = society.name
        society.delete()
        return Response(
            {"message": f"Gated Society '{society_name}' has been successfully deleted."},
            status=status.HTTP_200_OK,
        )
