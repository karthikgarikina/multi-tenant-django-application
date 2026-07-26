from django.core import management
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from app.middleware import SAFE_IDENTIFIER, reset_search_path
from app.models import Tenant


class Command(BaseCommand):
    help = "Create a tenant schema and run Django migrations inside it."

    def add_arguments(self, parser):
        parser.add_argument("tenant_id", type=str)

    def handle(self, *args, **options):
        tenant_id = options["tenant_id"]

        reset_search_path()
        try:
            tenant = Tenant.objects.get(tenant_id=tenant_id)
        except Tenant.DoesNotExist as exc:
            raise CommandError(f'Tenant "{tenant_id}" not found in public schema.') from exc

        schema_name = tenant.db_schema
        if not SAFE_IDENTIFIER.match(schema_name):
            raise CommandError(f'Unsafe PostgreSQL schema name "{schema_name}".')

        quoted_schema = connection.ops.quote_name(schema_name)
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {quoted_schema}")
            cursor.execute(f"SET search_path TO {quoted_schema}")

        self.stdout.write(self.style.SUCCESS(f'Schema "{schema_name}" is ready.'))
        management.call_command("migrate", "--fake-initial", interactive=False, verbosity=options["verbosity"])

        reset_search_path()
        self.stdout.write(self.style.SUCCESS(f'Migrations completed for "{tenant_id}".'))
