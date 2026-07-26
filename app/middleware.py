import json
import re

import redis
from django.conf import settings
from django.db import connection
from django.http import JsonResponse

from .context import clear_current_tenant, set_current_tenant
from .models import Tenant


TENANT_HEADER = "X-Tenant-ID"
RLS_PREFIX = "/api/rls/"
SCHEMA_PREFIX = "/api/schema/"
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def reset_search_path():
    with connection.cursor() as cursor:
        cursor.execute("SET search_path TO public")


def set_schema_search_path(schema_name):
    if not SAFE_IDENTIFIER.match(schema_name):
        raise ValueError(f"Unsafe PostgreSQL schema name: {schema_name}")
    quoted_schema = connection.ops.quote_name(schema_name)
    with connection.cursor() as cursor:
        cursor.execute(f"SET search_path TO {quoted_schema}, public")


def _redis_client():
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def _tenant_from_cache(tenant_id):
    try:
        payload = _redis_client().get(f"tenant:{tenant_id}")
    except redis.RedisError:
        return None
    if not payload:
        return None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return Tenant(
        id=data["id"],
        name=data["name"],
        tenant_id=data["tenant_id"],
        db_schema=data["db_schema"],
    )


def _cache_tenant(tenant):
    payload = json.dumps(
        {
            "id": tenant.id,
            "name": tenant.name,
            "tenant_id": tenant.tenant_id,
            "db_schema": tenant.db_schema,
        }
    )
    try:
        _redis_client().setex(
            f"tenant:{tenant.tenant_id}",
            settings.TENANT_CACHE_TTL_SECONDS,
            payload,
        )
    except redis.RedisError:
        pass


def get_tenant(tenant_id):
    tenant = _tenant_from_cache(tenant_id)
    if tenant is not None:
        return tenant

    reset_search_path()
    tenant = Tenant.objects.get(tenant_id=tenant_id)
    _cache_tenant(tenant)
    return tenant


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        clear_current_tenant()
        request.tenant = None

        uses_rls = request.path.startswith(RLS_PREFIX)
        uses_schema = request.path.startswith(SCHEMA_PREFIX)
        if not uses_rls and not uses_schema:
            return self.get_response(request)

        tenant_id = request.headers.get(TENANT_HEADER)
        if not tenant_id:
            return JsonResponse({"detail": "X-Tenant-ID header is required."}, status=404)

        try:
            tenant = get_tenant(tenant_id)
        except Tenant.DoesNotExist:
            return JsonResponse({"detail": "Tenant not found."}, status=404)

        request.tenant = tenant
        set_current_tenant(tenant)

        try:
            if uses_schema:
                set_schema_search_path(tenant.db_schema)
            else:
                reset_search_path()
            return self.get_response(request)
        finally:
            reset_search_path()
            clear_current_tenant()
