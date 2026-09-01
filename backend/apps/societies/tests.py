"""Tests for GatedSociety CRUD and role permissions matching mentor checklist."""

from django.test import TestCase
from django.contrib.auth.models import Group
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import Profile
from apps.societies.models import GatedSociety


class GatedSocietyTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Seed groups
        self.super_admin_group = Group.objects.create(id=1, name="Super Admin")
        self.admin_group = Group.objects.create(id=2, name="Admin")
        self.sub_admin_group = Group.objects.create(id=3, name="Sub Admin")
        self.volunteer_group = Group.objects.create(id=4, name="Volunteer")
        self.guardian_group = Group.objects.create(id=5, name="Guardian")

        # Create two societies
        self.society_a = GatedSociety.objects.create(
            name="Palm Meadows Alpha",
            owner="Alpha Holdings",
            in_charge="Manager Rao",
        )
        self.society_b = GatedSociety.objects.create(
            name="Palm Meadows Beta",
            owner="Beta Enterprises",
            in_charge="Manager Das",
        )

        # Users
        self.admin_user = Profile.objects.create_user(
            email="admin@society.org",
            mobile="+919876599001",
            password="Password123!",
            group=self.admin_group,
        )
        self.sub_admin_user = Profile.objects.create_user(
            email="subadmin@alpha.org",
            mobile="+919876599002",
            password="Password123!",
            group=self.sub_admin_group,
            gated_society=self.society_a,
        )
        self.guardian_user = Profile.objects.create_user(
            email="guardian@alpha.org",
            mobile="+919876599003",
            password="Password123!",
            group=self.guardian_group,
            gated_society=self.society_a,
        )

    def _get_token(self, email, password="Password123!"):
        res = self.client.post("/api/auth/login/", {"email": email, "password": password})
        return res.data["access"]

    def test_create_society_admin_only(self):
        """MENTOR SPEC: Admin only can create a gated society."""
        # 1. Admin creates -> 201 Created
        token = self._get_token("admin@society.org")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        payload = {
            "name": "Lotus Gardens",
            "owner": "Lotus Developers",
            "in_charge": "Chief Officer Khan",
        }
        res = self.client.post("/api/societies/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["name"], "Lotus Gardens")

        # 2. Sub Admin tries to create -> 403 Forbidden
        sub_token = self._get_token("subadmin@alpha.org")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {sub_token}")
        res2 = self.client.post("/api/societies/", payload, format="json")
        self.assertEqual(res2.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Guardian tries to create -> 403 Forbidden
        guardian_token = self._get_token("guardian@alpha.org")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {guardian_token}")
        res3 = self.client.post("/api/societies/", payload, format="json")
        self.assertEqual(res3.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_societies_role_filtering(self):
        """MENTOR SPEC: Admin sees all societies; every other role sees only their own."""
        # 1. Admin sees both societies (2 total)
        admin_token = self._get_token("admin@society.org")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_token}")
        res_admin = self.client.get("/api/societies/")
        self.assertEqual(res_admin.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_admin.data), 2)

        # 2. Sub-admin affiliated with Alpha sees ONLY Alpha (1 total)
        sub_token = self._get_token("subadmin@alpha.org")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {sub_token}")
        res_sub = self.client.get("/api/societies/")
        self.assertEqual(res_sub.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_sub.data), 1)
        self.assertEqual(res_sub.data[0]["id"], self.society_a.id)

        # 3. Guardian affiliated with Alpha sees ONLY Alpha (1 total)
        guardian_token = self._get_token("guardian@alpha.org")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {guardian_token}")
        res_guardian = self.client.get("/api/societies/")
        self.assertEqual(res_guardian.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_guardian.data), 1)
        self.assertEqual(res_guardian.data[0]["id"], self.society_a.id)

    def test_edit_society_where_condition_and_permissions(self):
        """MENTOR SPEC: Edit must use real WHERE-condition on specific ID.

        Admin can edit any society; Sub Admin can edit only their own society.
        """
        # 1. Sub Admin editing own society (Alpha) -> 200 OK
        sub_token = self._get_token("subadmin@alpha.org")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {sub_token}")
        res = self.client.patch(f"/api/societies/{self.society_a.id}/", {"in_charge": "Supervisor Kumar"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["in_charge"], "Supervisor Kumar")

        # 2. Sub Admin trying to edit other society (Beta) -> 403 Forbidden
        res_other = self.client.patch(f"/api/societies/{self.society_b.id}/", {"in_charge": "Hacked In Charge"}, format="json")
        self.assertEqual(res_other.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Admin editing other society (Beta) -> 200 OK
        admin_token = self._get_token("admin@society.org")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_token}")
        res_admin = self.client.patch(f"/api/societies/{self.society_b.id}/", {"name": "Palm Meadows Beta Heights"}, format="json")
        self.assertEqual(res_admin.status_code, status.HTTP_200_OK)
        self.assertEqual(res_admin.data["name"], "Palm Meadows Beta Heights")

        # 4. Non-existent ID -> 404 Not Found (exact WHERE condition)
        res_404 = self.client.patch("/api/societies/99999/", {"name": "Ghost Society"}, format="json")
        self.assertEqual(res_404.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_society_permissions(self):
        """MENTOR SPEC: Delete must use real WHERE-condition on specific ID."""
        # 1. Guardian trying to delete -> 403 Forbidden
        guardian_token = self._get_token("guardian@alpha.org")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {guardian_token}")
        res_guardian = self.client.delete(f"/api/societies/{self.society_a.id}/")
        self.assertEqual(res_guardian.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Admin deleting Beta -> 200 OK
        admin_token = self._get_token("admin@society.org")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_token}")
        res_admin = self.client.delete(f"/api/societies/{self.society_b.id}/")
        self.assertEqual(res_admin.status_code, status.HTTP_200_OK)
        self.assertFalse(GatedSociety.objects.filter(id=self.society_b.id).exists())
