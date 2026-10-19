from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
from .views import (AreaViewSet, DeviceViewSet, MyLocationView, MyProfileView, PropertyViewSet,
                    RegistrationView, TokenLoginView, UserViewSet, IncidentViewSet, SafetyPostViewSet,
                    VolunteerApplicationView) # 1. Import the new view

# The router automatically generates standard REST URLs for our ViewSets
router = DefaultRouter()
router.register(r'users', UserViewSet)
router.register(r'areas', AreaViewSet)
router.register(r'properties', PropertyViewSet, basename='property')
router.register(r'devices', DeviceViewSet, basename='device')
router.register(r'incidents', IncidentViewSet)
router.register(r'posts', SafetyPostViewSet)

urlpatterns = [
    # API Endpoints
    path('', include(router.urls)),

    # Mobile authentication and profile endpoints.
    path('auth/login/', TokenLoginView.as_view(), name='api_token_login'),
    path('auth/register/', RegistrationView.as_view(), name='api_register'),
    path('auth/volunteer/apply/', VolunteerApplicationView.as_view(), name='api_apply_volunteer'), # 2. Add the application endpoint
    path('me/', MyProfileView.as_view(), name='api_me'),
    path('me/location/', MyLocationView.as_view(), name='api_my_location'),

    # Compatibility endpoint for clients expecting DRF's token-only response.
    path('login/', obtain_auth_token, name='api_token_auth'),
]