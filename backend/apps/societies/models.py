"""GatedSociety model matching mentor assignment schema."""

from django.db import models
from django.conf import settings


class GatedSociety(models.Model):
    """Gated Society database model.

    Table name: gated_society
    Fields: id, name, owner, in_charge, created_at, updated_at, sub_admin_id
    """
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255, db_index=True)
    owner = models.CharField(max_length=255)
    in_charge = models.CharField(max_length=255)
    sub_admin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='sub_admin_id',
        related_name='managed_societies',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'gated_society'
        verbose_name = 'Gated Society'
        verbose_name_plural = 'Gated Societies'
        ordering = ['-created_at']

    def __str__(self):
        return self.name
