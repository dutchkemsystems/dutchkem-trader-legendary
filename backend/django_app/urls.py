# backend/django_app/urls.py — add health and metrics endpoints
from django.urls import path
from django_app.views import health_check

urlpatterns = [
    path("health/", health_check, name="health"),
]

# Metrics endpoint (added separately to avoid import issues)
from django.http import HttpResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

def metrics_view(request):
    return HttpResponse(generate_latest(), content_type=CONTENT_TYPE_LATEST)

urlpatterns += [
    path("metrics/", metrics_view, name="metrics"),
]
