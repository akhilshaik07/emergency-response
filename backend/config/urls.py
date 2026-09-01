"""URL configuration for Emergency Response Platform project."""

from django.urls import path, include

urlpatterns = [
    path('api/auth/', include('apps.accounts.urls_auth')),
    path('api/profile/', include('apps.accounts.urls_profile')),
    path('api/societies/', include('apps.societies.urls')),
    path('api/alerts/', include('apps.alerts.urls')),
]
