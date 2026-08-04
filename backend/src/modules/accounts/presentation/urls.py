from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CompanyView, CompanyViewSet, UserGroupViewSet, UserViewSet

router = DefaultRouter()
router.register("users", UserViewSet, basename="user")
router.register("user-groups", UserGroupViewSet, basename="user-group")
router.register("companies", CompanyViewSet, basename="company")

urlpatterns = [
    path("company", CompanyView.as_view(), name="my-company"),
    path("", include(router.urls)),
]
