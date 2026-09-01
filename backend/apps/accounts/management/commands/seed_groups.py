"""Management command to seed auth_group roles."""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group

ROLES = [
    (1, "Super Admin"),
    (2, "Admin"),
    (3, "Sub Admin"),
    (4, "Volunteer"),
    (5, "Guardian"),
]

class Command(BaseCommand):
    help = "Seed required auth_group roles (1=Super Admin, 2=Admin, 3=Sub Admin, 4=Volunteer, 5=Guardian)"

    def handle(self, *args, **options):
        for role_id, role_name in ROLES:
            group, created = Group.objects.update_or_create(
                id=role_id,
                defaults={'name': role_name}
            )
            action = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"{action} Group {role_id}: {role_name}"))
        self.stdout.write(self.style.SUCCESS("All 5 auth_group roles seeded successfully."))
