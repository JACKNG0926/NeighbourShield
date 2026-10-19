from django.contrib.auth import authenticate
from math import asin, cos, radians, sin, sqrt
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated, SAFE_METHODS
from rest_framework.authtoken.models import Token
from django.core.exceptions import ValidationError as DjangoValidationError
from .models import Area, Device, Property, User, Incident, SafetyPost, EscalationPolicy
from .permissions import IsTownshipAdmin
from .serializers import (AreaSerializer, DeviceSerializer, LocationUpdateSerializer,
                          MobileProfileSerializer, PropertySerializer, RegistrationSerializer,
                          UserSerializer, IncidentSerializer, SafetyPostSerializer)


class TokenLoginView(APIView):
    """Flutter-friendly login that returns both a token and the mobile profile."""
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username', '')
        password = request.data.get('password', '')
        user = authenticate(request, username=username, password=password)
        if not user or not user.is_active:
            return Response({'detail': 'Invalid username or password.'}, status=status.HTTP_400_BAD_REQUEST)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({'token': token.key, 'user': MobileProfileSerializer(user).data})


class RegistrationView(APIView):
    """Residents can create only resident accounts; roles remain admin controlled."""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token = Token.objects.create(user=user)
        return Response({'token': token.key, 'user': MobileProfileSerializer(user).data},
                        status=status.HTTP_201_CREATED)


class MyProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(MobileProfileSerializer(request.user).data)

    def patch(self, request):
        serializer = MobileProfileSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class MyLocationView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request):
        serializer = LocationUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request.user.last_latitude = serializer.validated_data['latitude']
        request.user.last_longitude = serializer.validated_data['longitude']
        request.user.last_location_at = timezone.now()
        request.user.save(update_fields=['last_latitude', 'last_longitude', 'last_location_at'])
        return Response({'detail': 'Location updated.'})


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsTownshipAdmin]


class AreaViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Area.objects.all().order_by('name')
    serializer_class = AreaSerializer
    permission_classes = [IsAuthenticated]


class PropertyViewSet(viewsets.ModelViewSet):
    serializer_class = PropertySerializer

    def get_queryset(self):
        queryset = Property.objects.select_related('area').all()
        if self.request.user.is_township_admin:
            return queryset
        if self.request.user.residence_id:
            return queryset.filter(pk=self.request.user.residence_id)
        return queryset.none()

    def get_permissions(self):
        permission_class = IsAuthenticated if self.request.method in SAFE_METHODS else IsTownshipAdmin
        return [permission_class()]


class DeviceViewSet(viewsets.ModelViewSet):
    serializer_class = DeviceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Device.objects.filter(user=self.request.user).order_by('-last_seen')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class IncidentViewSet(viewsets.ModelViewSet):
    queryset = Incident.objects.all().order_by('-created_at')
    serializer_class = IncidentSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'head', 'options']

    @staticmethod
    def _distance_meters(lat1, lon1, lat2, lon2):
        """Haversine distance between two coordinates, returned in metres."""
        earth_radius_m = 6_371_000
        lat1, lon1, lat2, lon2 = map(radians, [float(lat1), float(lon1), float(lat2), float(lon2)])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        return earth_radius_m * 2 * asin(sqrt(min(1.0, a)))

    def get_queryset(self):
        user = self.request.user
        if user.is_township_admin or user.role == 'security':
            return Incident.objects.all().order_by('-created_at')

        # Verified volunteers can only see nearby SOS incidents that still
        # need a response. Never expose the full township incident list to a
        # volunteer who is not currently eligible or has stale location data.
        if user.role == 'volunteer':
            if (not user.is_eligible_volunteer or not user.has_fresh_location()
                    or user.last_longitude is None):
                return Incident.objects.none()

            policy = EscalationPolicy.get_solo()
            candidates = Incident.objects.filter(
                status__in=Incident.AWAITING_ACK_STATUSES,
            ).exclude(user=user).only('id', 'latitude', 'longitude').order_by('-created_at')

            nearby_ids = []
            for incident in candidates:
                distance = self._distance_meters(
                    user.last_latitude,
                    user.last_longitude,
                    incident.latitude,
                    incident.longitude,
                )
                if distance <= policy.volunteer_radius_m:
                    nearby_ids.append(incident.pk)

            return Incident.objects.filter(pk__in=nearby_ids).select_related('user').order_by('-created_at')

        # Residents can see only their own incidents.
        return Incident.objects.filter(user=user).order_by('-created_at')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        incident = Incident.create_sos(user=request.user, **serializer.validated_data)
        return Response(self.get_serializer(incident).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def acknowledge(self, request, pk=None):
        try:
            incident, acknowledgement, is_first = Incident.acknowledge(
                incident_id=self.get_object().pk,
                responder=request.user,
                eta_minutes=request.data.get('eta_minutes'),
                note=request.data.get('note', ''),
            )
        except DjangoValidationError as exc:
            return Response({'detail': exc.messages}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'incident': self.get_serializer(incident).data,
            'acknowledgement_id': acknowledgement.pk,
            'is_first_acknowledgement': is_first,
        })


class SafetyPostViewSet(viewsets.ModelViewSet):
    queryset = SafetyPost.objects.all().order_by('-created_at')
    serializer_class = SafetyPostSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.action in ('list', 'retrieve') or self.request.user.is_township_admin:
            return SafetyPost.objects.all().order_by('-created_at')
        return SafetyPost.objects.filter(author=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


class VolunteerApplicationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user

        if user.is_verified_volunteer:
            return Response(
                {"detail": "You are already a verified volunteer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.is_volunteer_opted_in = True
        user.save(update_fields=["is_volunteer_opted_in"])

        return Response(
            {
                "detail": (
                    "Volunteer application submitted successfully."
                )
            },
            status=status.HTTP_200_OK,
        )