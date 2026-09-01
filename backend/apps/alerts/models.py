"""SosAlert model matching mentor assignment schema (logic deferred)."""

from django.db import models
from django.conf import settings


class SosAlert(models.Model):
    """SOS Alert database schema.

    Table name: sos_alert
    Fields: id, user_id (FK -> profile), lat, long, response, issue, reached, created_at, updated_at
    """
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column='user_id',
        related_name='sos_alerts',
    )
    lat = models.DecimalField(max_digits=9, decimal_places=6)
    long = models.DecimalField(max_digits=9, decimal_places=6)
    response = models.TextField(blank=True, null=True)
    issue = models.CharField(max_length=100)
    reached = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sos_alert'
        verbose_name = 'SOS Alert'
        verbose_name_plural = 'SOS Alerts'
        ordering = ['-created_at']

    def __str__(self):
        return f"SOS #{self.id} - User {self.user_id} ({self.issue})"
