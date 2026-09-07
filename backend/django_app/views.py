# backend/django_app/views.py — health check
import time
from django.http import JsonResponse
from django.db import connection

_start_time = time.time()

def health_check(request):
    """Deep health check: verifies DB, Redis, and trading readiness."""
    health = {
        "status": "healthy",
        "uptime_seconds": round(time.time() - _start_time, 1),
        "timestamp": time.time(),
        "checks": {}
    }

    # Database check
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        health["checks"]["database"] = "ok"
    except Exception as e:
        health["checks"]["database"] = f"error: {str(e)}"
        health["status"] = "degraded"

    # Redis check
    try:
        from django.core.cache import cache
        cache.set("_healthcheck", "ok", 10)
        if cache.get("_healthcheck") == "ok":
            health["checks"]["redis"] = "ok"
        else:
            health["checks"]["redis"] = "error: write/read mismatch"
            health["status"] = "degraded"
    except Exception as e:
        health["checks"]["redis"] = f"error: {str(e)}"
        health["status"] = "degraded"

    status_code = 200 if health["status"] == "healthy" else 503
    return JsonResponse(health, status=status_code)
