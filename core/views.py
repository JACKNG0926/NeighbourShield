from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import ValidationError as DjangoValidationError
from .models import Device, Property, User, Incident, SafetyPost
from .permissions import IsTownshipAdmin
from .serializers import (DeviceSerializer, PropertySerializer, UserSerializer, IncidentSerializer,
                          SafetyPostSerializer)


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsTownshipAdmin]


class PropertyViewSet(viewsets.ModelViewSet):
    queryset = Property.objects.select_related('area').all()
    serializer_class = PropertySerializer
    permission_classes = [IsTownshipAdmin]


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

    def get_queryset(self):
        user = self.request.user
        if user.is_township_admin or user.role == 'security':
            return Incident.objects.all().order_by('-created_at')
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
