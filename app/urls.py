from rest_framework.routers import DefaultRouter

from .views import RLSProjectViewSet, SchemaProjectViewSet


router = DefaultRouter()
router.register("rls/projects", RLSProjectViewSet, basename="rls-projects")
router.register("schema/projects", SchemaProjectViewSet, basename="schema-projects")

urlpatterns = router.urls
