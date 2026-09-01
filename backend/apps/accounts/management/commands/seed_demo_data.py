"""Management command to seed test societies and demo accounts for all 5 roles."""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group
from apps.accounts.models import Profile
from apps.societies.models import GatedSociety

ROLES = [
    (1, "Super Admin"),
    (2, "Admin"),
    (3, "Sub Admin"),
    (4, "Volunteer"),
    (5, "Guardian"),
]

class Command(BaseCommand):
    help = "Seed demo roles, societies, and accounts for Postman testing."

    def handle(self, *args, **options):
        # 1. Seed Groups
        groups = {}
        for role_id, role_name in ROLES:
            group, _ = Group.objects.update_or_create(id=role_id, defaults={'name': role_name})
            groups[role_id] = group

        # 2. Seed Society
        society, _ = GatedSociety.objects.update_or_create(
            name="Greenwood Palms Estate",
            defaults={
                'owner': "Greenwood Developers Ltd",
                'in_charge': "Captain Roy (Security Head)",
            }
        )
        society2, _ = GatedSociety.objects.update_or_create(
            name="Palm Meadows Alpha",
            defaults={
                'owner': "Meadows Infra Corp",
                'in_charge': "Supervisor Das",
            }
        )

        # 3. Seed Demo Users
        demo_users = [
            {
                "email": "superadmin@emergency.org",
                "mobile": "+919800000001",
                "first_name": "Super",
                "last_name": "Admin",
                "group_id": 1,
                "is_staff": True,
                "is_superuser": True,
            },
            {
                "email": "admin@emergency.org",
                "mobile": "+919800000002",
                "first_name": "Chief",
                "last_name": "Admin",
                "group_id": 2,
                "is_staff": True,
            },
            {
                "email": "subadmin@greenwood.org",
                "mobile": "+919800000003",
                "first_name": "Suresh",
                "last_name": "Kumar",
                "group_id": 3,
                "gated_society": society,
            },
            {
                "email": "volunteer@emergency.org",
                "mobile": "+919800000004",
                "first_name": "Pooja",
                "last_name": "Sharma",
                "group_id": 4,
            },
            {
                "email": "guardian@greenwood.org",
                "mobile": "+919800000005",
                "first_name": "Aarav",
                "last_name": "Patel",
                "group_id": 5,
                "gated_society": society,
                "emergency_contact1": {"name": "Pooja Patel", "mobile": "+919800000099", "relationship": "Spouse"},
                "emergency_contact2": {"name": "Vikram Patel", "mobile": "+919800000088", "relationship": "Brother"},
                "medical_condition": {"blood_group": "O+", "allergies": "Penicillin"},
            },
        ]

        for user_data in demo_users:
            email = user_data["email"]
            group_id = user_data.pop("group_id")
            gated_soc = user_data.pop("gated_society", None)
            
            user = Profile.objects.filter(email=email).first()
            if not user:
                user = Profile.objects.create_user(
                    password="Password123!",
                    group=groups[group_id],
                    gated_society=gated_soc,
                    **user_data
                )
                self.stdout.write(self.style.SUCCESS(f"Created demo user: {email} (Role: {groups[group_id].name})"))
            else:
                user.group = groups[group_id]
                user.gated_society = gated_soc
                user.set_password("Password123!")
                user.save()
                self.stdout.write(self.style.SUCCESS(f"Updated demo user: {email}"))

        self.stdout.write(self.style.SUCCESS("\nAll demo data ready! Standard password for all demo accounts: Password123!"))
