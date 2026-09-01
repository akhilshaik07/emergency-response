"""Profile URLs."""

from django.urls import path
from apps.accounts.views import ProfileMeView

urlpatterns = [
    path('me/', ProfileMeView.as_view(), name='profile_me'),
]
