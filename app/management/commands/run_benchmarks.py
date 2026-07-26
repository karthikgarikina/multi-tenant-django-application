import json
import os
import statistics
import time

from django.core.management.base import BaseCommand
from django.db import connection

from app.middleware import SAFE_IDENTIFIER, reset_search_path, set_schema_search_path


class Command(BaseCommand):
    help = "Run performance benchmarks for row-level tenancy and schema-per-tenant isolation."

    def handle(self, *args, **options):
        tenant_count = int(os.environ.get("BENCHMARK_TENANTS", "10"))
        projects_per_tenant = int(os.environ.get("BENCHMARK_PROJECTS_PER_TENANT", "10000"))

        tenant_rows = self._prepare_public_tenants(tenant_count)
        target_tenant_id = tenant_rows[0][0]
        target_schema = tenant_rows[0][2]

        self.stdout.write("Preparing row-level benchmark data...")
        self._prepare_rls_projects(tenant_rows, projects_per_tenant)

        self.stdout.write("Measuring row-level queries...")
        self._drop_composite_index()
        without_index = self._average_explain_time(
            "SELECT id, name, tenant_id, created_at FROM public.app_project "
            "WHERE tenant_id = %s ORDER BY created_at DESC LIMIT 100",
            [target_tenant_id],
        )
        self._create_composite_index()
        with_index = self._average_explain_time(
            "SELECT id, name, tenant_id, created_at FROM public.app_project "
            "WHERE tenant_id = %s ORDER BY created_at DESC LIMIT 100",
            [target_tenant_id],
        )
        rls_index_size = self._relation_size_kb("public.idx_app_project_tenant_created_at")

        self.stdout.write("Preparing schema-isolation benchmark data...")
        self._prepare_schema_projects(tenant_rows, projects_per_tenant)

        self.stdout.write("Measuring schema-isolation queries...")
        set_schema_search_path(target_schema)
        schema_time = self._average_explain_time(
            "SELECT id, name, tenant_id, created_at FROM app_project ORDER BY created_at DESC LIMIT 100",
            [],
        )
        schema_index_size = self._relation_size_kb(f"{target_schema}.idx_app_project_created_at")
        overhead = self._measure_search_path_overhead(target_schema)
        reset_search_path()

        results = {
            "row_level": {
                "query_time_ms": {
                    "without_index": without_index,
                    "with_index": with_index,
                },
                "index_size_kb": rls_index_size,
            },
            "schema_isolation": {
                "query_time_ms": schema_time,
                "index_size_kb": schema_index_size,
            },
            "connection_overhead_ms": {
                "set_search_path": overhead,
            },
        }

        os.makedirs("results", exist_ok=True)
        with open("results/benchmarks.json", "w", encoding="utf-8") as output:
            json.dump(results, output, indent=2)

        self.stdout.write(self.style.SUCCESS("Benchmarks complete: results/benchmarks.json"))

    def _prepare_public_tenants(self, tenant_count):
        rows = []
        with connection.cursor() as cursor:
            reset_search_path()
            for index in range(tenant_count):
                tenant_id = f"bench_tenant_{index + 1}"
                name = f"Benchmark Tenant {index + 1}"
                schema = f"schema_bench_tenant_{index + 1}"
                cursor.execute(
                    """
                    INSERT INTO public.tenants (tenant_id, name, db_schema)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (tenant_id)
                    DO UPDATE SET name = EXCLUDED.name, db_schema = EXCLUDED.db_schema
                    RETURNING id, tenant_id, db_schema
                    """,
                    [tenant_id, name, schema],
                )
                tenant_pk, stored_tenant_id, stored_schema = cursor.fetchone()
                rows.append((tenant_pk, stored_tenant_id, stored_schema))
        return rows

    def _prepare_rls_projects(self, tenant_rows, projects_per_tenant):
        tenant_ids = [row[0] for row in tenant_rows]
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM public.app_project WHERE tenant_id = ANY(%s)", [tenant_ids])
            for tenant_pk, tenant_id, _schema in tenant_rows:
                cursor.execute(
                    """
                    INSERT INTO public.app_project (tenant_id, name, created_at)
                    SELECT %s, %s || gs::text, NOW() - (gs || ' seconds')::interval
                    FROM generate_series(1, %s) AS gs
                    """,
                    [tenant_pk, f"RLS {tenant_id} Project ", projects_per_tenant],
                )

    def _prepare_schema_projects(self, tenant_rows, projects_per_tenant):
        with connection.cursor() as cursor:
            for _tenant_pk, tenant_id, schema in tenant_rows:
                if not SAFE_IDENTIFIER.match(schema):
                    raise ValueError(f"Unsafe PostgreSQL schema name: {schema}")
                quoted_schema = connection.ops.quote_name(schema)
                cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {quoted_schema}")
                cursor.execute(f"DROP TABLE IF EXISTS {quoted_schema}.app_project")
                cursor.execute(
                    f"""
                    CREATE TABLE {quoted_schema}.app_project (
                        id BIGSERIAL PRIMARY KEY,
                        tenant_id BIGINT NULL,
                        name VARCHAR(200) NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    f"CREATE INDEX idx_app_project_created_at ON {quoted_schema}.app_project (created_at DESC)"
                )
                cursor.execute(
                    f"""
                    INSERT INTO {quoted_schema}.app_project (name, created_at)
                    SELECT %s || gs::text, NOW() - (gs || ' seconds')::interval
                    FROM generate_series(1, %s) AS gs
                    """,
                    [f"Schema {tenant_id} Project ", projects_per_tenant],
                )

    def _drop_composite_index(self):
        with connection.cursor() as cursor:
            cursor.execute("DROP INDEX IF EXISTS public.idx_app_project_tenant_created_at")

    def _create_composite_index(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_app_project_tenant_created_at "
                "ON public.app_project (tenant_id, created_at DESC)"
            )

    def _average_explain_time(self, sql, params):
        timings = []
        with connection.cursor() as cursor:
            for _ in range(5):
                cursor.execute(f"EXPLAIN (ANALYZE, FORMAT JSON) {sql}", params)
                plan = cursor.fetchone()[0][0]
                timings.append(float(plan["Execution Time"]))
        return round(statistics.mean(timings), 4)

    def _relation_size_kb(self, qualified_name):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_relation_size(%s::regclass) / 1024.0", [qualified_name])
            return round(float(cursor.fetchone()[0]), 4)

    def _measure_search_path_overhead(self, schema_name):
        if not SAFE_IDENTIFIER.match(schema_name):
            raise ValueError(f"Unsafe PostgreSQL schema name: {schema_name}")
        quoted_schema = connection.ops.quote_name(schema_name)
        iterations = 200
        start = time.perf_counter()
        with connection.cursor() as cursor:
            for _ in range(iterations):
                cursor.execute(f"SET search_path TO {quoted_schema}, public")
        elapsed = time.perf_counter() - start
        return round((elapsed / iterations) * 1000, 4)
