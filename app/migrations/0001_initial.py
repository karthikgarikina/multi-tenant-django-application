from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Tenant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("tenant_id", models.CharField(max_length=100, unique=True)),
                ("db_schema", models.CharField(max_length=100, unique=True)),
            ],
            options={
                "db_table": "tenants",
                "ordering": ["tenant_id"],
            },
        ),
    ]
