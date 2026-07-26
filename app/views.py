from rest_framework import viewsets

from .models import Project
from .serializers import ProjectSerializer


class RLSProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer

    def get_queryset(self):
        return Project.objects.all().order_by("id")

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)


class SchemaProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer

    def get_queryset(self):
        return Project.all_objects.all().order_by("id")

    def perform_create(self, serializer):
        serializer.save(tenant=None)
