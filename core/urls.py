from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
from .views import UserViewSet, IncidentViewSet, SafetyPostViewSet

# The router automatically generates standard REST URLs for our ViewSets
router = DefaultRouter()
router.register(r'users', UserViewSet)
router.register(r'incidents', IncidentViewSet)
router.register(r'posts', SafetyPostViewSet)

urlpatterns = [
    # API Endpoints
    path('', include(router.urls)),

    # Token Authentication Endpoint (Flutter sends POST with username/password here)
    path('login/', obtain_auth_token, name='api_token_auth'),
]