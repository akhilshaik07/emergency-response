"""Tests for Accounts and Profile authentication/permissions matching mentor checklist."""

from django.test import TestCase
from django.contrib.auth.models import Group
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import Profile
from apps.societies.models import GatedSociety


class AuthAndProfileTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Seed groups
        self.super_admin_group = Group.objects.create(id=1, name="Super Admin")
        self.admin_group = Group.objects.create(id=2, name="Admin")
        self.sub_admin_group = Group.objects.create(id=3, name="Sub Admin")
        self.volunteer_group = Group.objects.create(id=4, name="Volunteer")
        self.guardian_group = Group.objects.create(id=5, name="Guardian")

        # Create a society
        self.society = GatedSociety.objects.create(
            name="Greenwood Palms Estate",
            owner="Mr. Sharma",
            in_charge="Security Captain Roy",
        )

        # Create a test resident (Guardian)
        self.resident = Profile.objects.create_user(
            email="resident@example.com",
            mobile="+919876500001",
            password="Password123!",
            first_name="Aarav",
            last_name="Patel",
            group=self.guardian_group,
            gated_society=self.society,
            emergency_contact1={"name": "Pooja Patel", "mobile": "+919876500099", "relationship": "Spouse"},
            medical_condition={"allergies": "Penicillin", "blood_group": "O+"},
        )

        # Create an Admin user
        self.admin = Profile.objects.create_user(
            email="admin@example.com",
            mobile="+919876500002",
            password="AdminPassword123!",
            group=self.admin_group,
        )

    def test_register_public_user_success(self):
        payload = {
            "email": "new.resident@example.com",
            "mobile": "+919876500003",
            "password": "StrongPassword123!",
            "first_name": "Rohan",
            "last_name": "Gupta",
            "group_id": 5,
            "gated_society_id": self.society.id,
            "emergency_contact1": {"name": "Sita Gupta", "mobile": "+919876500088", "relationship": "Mother"},
        }
        response = self.client.post("/api/auth/register/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["email"], "new.resident@example.com")
        self.assertEqual(response.data["mobile"], "+919876500003")

    def test_register_admin_role_rejected(self):
        """MENTOR SPEC: Admin (2) and Super Admin (1) cannot self-register."""
        for role_id in [1, 2]:
            payload = {
                "email": f"hacker.admin{role_id}@example.com",
                "mobile": f"+91987650001{role_id}",
                "password": "Password123!",
                "group_id": role_id,
            }
            response = self.client.post("/api/auth/register/", payload, format="json")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("not permitted", str(response.data))

    def test_login_with_email_success(self):
        """MENTOR SPEC: Login must accept email + password."""
        payload = {
            "email": "resident@example.com",
            "password": "Password123!",
        }
        response = self.client.post("/api/auth/login/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["user"]["email"], "resident@example.com")

    def test_login_with_mobile_success(self):
        """MENTOR SPEC: Login must accept mobile + password."""
        payload = {
            "mobile": "+919876500001",
            "password": "Password123!",
        }
        response = self.client.post("/api/auth/login/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_login_with_username_only_rejected(self):
        """MENTOR SPEC: Login MUST NOT accept username as the login identifier."""
        payload = {
            "username": "resident@example.com",
            "password": "Password123!",
        }
        response = self.client.post("/api/auth/login/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_wrong_password_rejected(self):
        payload = {
            "email": "resident@example.com",
            "password": "WrongPassword!",
        }
        response = self.client.post("/api/auth/login/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["non_field_errors"][0], "Invalid email/mobile or password.")

    def test_login_inactive_user_rejected(self):
        self.resident.is_active = False
        self.resident.save()

        payload = {
            "email": "resident@example.com",
            "password": "Password123!",
        }
        response = self.client.post("/api/auth/login/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_profile_me_get_and_token_scoping(self):
        """MENTOR SPEC: Profile /me/ must scope strictly to user decoded from JWT."""
        login_res = self.client.post("/api/auth/login/", {"email": "resident@example.com", "password": "Password123!"})
        token = login_res.data["access"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = self.client.get("/api/profile/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "resident@example.com")
        self.assertEqual(response.data["medical_condition"]["blood_group"], "O+")

    def test_profile_me_patch_editable_fields(self):
        """MENTOR SPEC: Editable fields include email, first_name, last_name, mobile, emergency contacts."""
        login_res = self.client.post("/api/auth/login/", {"email": "resident@example.com", "password": "Password123!"})
        token = login_res.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        patch_payload = {
            "first_name": "Aarav Updated",
            "mobile": "+919876500099",
            "emergency_contact2": {"name": "Vikram Patel", "mobile": "+919876500077", "relationship": "Brother"},
        }
        response = self.client.patch("/api/profile/me/", patch_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["first_name"], "Aarav Updated")
        self.assertEqual(response.data["mobile"], "+919876500099")
        self.assertEqual(response.data["emergency_contact2"]["name"], "Vikram Patel")

    def test_profile_me_patch_locked_and_forbidden_fields_cannot_be_modified(self):
        """MENTOR SPEC: Locked fields (gated_society_id, group_id) and forbidden fields (is_staff, is_active) cannot be self-edited."""
        login_res = self.client.post("/api/auth/login/", {"email": "resident@example.com", "password": "Password123!"})
        token = login_res.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        # Attempt to escalate group to Admin (2) and alter society and is_staff
        malicious_payload = {
            "group_id": 2,
            "gated_society_id": 999,
            "is_staff": True,
            "is_superuser": True,
        }
        response = self.client.patch("/api/profile/me/", malicious_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Refresh from database and verify none of these were modified
        self.resident.refresh_from_db()
        self.assertEqual(self.resident.group_id, 5)  # Still Guardian
        self.assertEqual(self.resident.gated_society_id, self.society.id)  # Unchanged
        self.assertFalse(self.resident.is_staff)
        self.assertFalse(self.resident.is_superuser)

    def test_profile_me_delete_soft_deletes_account(self):
        """MENTOR SPEC: DELETE /api/profile/me/ soft deletes the user account."""
        login_res = self.client.post("/api/auth/login/", {"email": "resident@example.com", "password": "Password123!"})
        token = login_res.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        del_res = self.client.delete("/api/profile/me/")
        self.assertEqual(del_res.status_code, status.HTTP_200_OK)

        self.resident.refresh_from_db()
        self.assertFalse(self.resident.is_active)

        # Subsequent login fails
        login_again = self.client.post("/api/auth/login/", {"email": "resident@example.com", "password": "Password123!"})
        self.assertEqual(login_again.status_code, status.HTTP_401_UNAUTHORIZED)
