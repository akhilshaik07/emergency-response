"""Societies URLs."""

from django.urls import path
from apps.societies.views import GatedSocietyListCreateView, GatedSocietyDetailView

urlpatterns = [
    path('', GatedSocietyListCreateView.as_view(), name='society_list_create'),
    path('<int:pk>/', GatedSocietyDetailView.as_view(), name='society_detail'),
]
