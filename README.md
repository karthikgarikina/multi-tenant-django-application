# Multi-Tenant Django API

Small Django REST API that compares two PostgreSQL multi-tenancy strategies:

- Row-level tenancy: shared `public.app_project` table with every row linked to `public.tenants`.
- Schema-per-tenant isolation: each tenant uses its own PostgreSQL schema, selected per request with `SET search_path`.

Redis is used to cache tenant lookups from the `X-Tenant-ID` request header.

## Start

1. Copy or edit environment values in `.env`.
2. Start everything:

```bash
docker-compose up --build
```

The app runs at `http://localhost:8000`. PostgreSQL seeds `tenant_a` and `tenant_b` automatically from `seeds/initial_tenants.sql`; the same tenants are listed in `submission.json`.

## API Checks

All tenant-protected API requests require `X-Tenant-ID`.

Create and list row-level projects:

```bash
curl -X POST http://localhost:8000/api/rls/projects/ \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: tenant_a" \
  -d "{\"name\":\"RLS Project One\"}"

curl http://localhost:8000/api/rls/projects/ -H "X-Tenant-ID: tenant_a"
curl http://localhost:8000/api/rls/projects/ -H "X-Tenant-ID: tenant_b"
```

Provision schemas before using schema-isolated projects:

```bash
docker-compose exec app python manage.py provision_tenant tenant_a
docker-compose exec app python manage.py provision_tenant tenant_b
```

Create and list schema-isolated projects:

```bash
curl -X POST http://localhost:8000/api/schema/projects/ \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: tenant_a" \
  -d "{\"name\":\"Schema Project One\"}"

curl http://localhost:8000/api/schema/projects/ -H "X-Tenant-ID: tenant_a"
curl http://localhost:8000/api/schema/projects/ -H "X-Tenant-ID: tenant_b"
```

Invalid or missing tenant headers return `404`:

```bash
curl -i http://localhost:8000/api/rls/projects/ -H "X-Tenant-ID: invalid_tenant"
```

## Benchmarks

Run:

```bash
docker-compose exec app python manage.py run_benchmarks
```

Output is written to `results/benchmarks.json`:

```json
{
  "row_level": {
    "query_time_ms": {
      "without_index": 123.45,
      "with_index": 12.34
    },
    "index_size_kb": 512.0
  },
  "schema_isolation": {
    "query_time_ms": 5.67,
    "index_size_kb": 50.0
  },
  "connection_overhead_ms": {
    "set_search_path": 0.12
  }
}
```

Use `.env` to change `BENCHMARK_TENANTS` and `BENCHMARK_PROJECTS_PER_TENANT`. The default is 10 tenants with 10,000 projects each.

## Trade-Off Summary

Row-level tenancy is simpler to operate and migrate, but every tenant-owned query must be scoped correctly. A composite index such as `(tenant_id, created_at)` is important for performance as the shared table grows.

Schema-per-tenant isolation gives stronger database-level separation and smaller per-tenant tables, but provisioning and migrations must run for each tenant schema. It also adds a small `SET search_path` cost per request.
