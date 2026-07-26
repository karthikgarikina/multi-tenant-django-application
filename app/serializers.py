from rest_framework import serializers

from .models import Project


class ProjectSerializer(serializers.ModelSerializer):
    tenant = serializers.SlugRelatedField(read_only=True, slug_field="tenant_id")

    class Meta:
        model = Project
        fields = ["id", "name", "tenant", "created_at"]
        read_only_fields = ["id", "tenant", "created_at"]
