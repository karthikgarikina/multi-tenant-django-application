from django.db import models

from .managers import TenantManager


class Tenant(models.Model):
    name = models.CharField(max_length=255)
    tenant_id = models.CharField(max_length=100, unique=True)
    db_schema = models.CharField(max_length=100, unique=True)

    class Meta:
        db_table = "tenants"
        ordering = ["tenant_id"]

    def __str__(self):
        return self.tenant_id


class Project(models.Model):
    tenant = models.ForeignKey(
        Tenant,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="projects",
        db_index=True,
    )
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.name
