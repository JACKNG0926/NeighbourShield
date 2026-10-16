from django.shortcuts import render

# Create your views here.
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from .models import User, Incident, SafetyPost
from .serializers import UserSerializer, IncidentSerializer, SafetyPostSerializer


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    # For a hackathon, we'll keep permissions simple. In production, restrict this.


class IncidentViewSet(viewsets.ModelViewSet):
    queryset = Incident.objects.all().order_by('-created_at')
    serializer_class = IncidentSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        # Automatically attach the logged-in user to the SOS incident
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'])
    def acknowledge(self, request, pk=None):
        incident = self.get_object()
        user = request.user

        if incident.status != 'pending':
            return Response({'detail': 'Incident already acknowledged or resolved.'},
                            status=status.HTTP_400_BAD_REQUEST)

        if user.role not in ['security', 'volunteer', 'admin']:
            return Response({'detail': 'Unauthorized to acknowledge.'}, status=status.HTTP_403_FORBIDDEN)

        incident.status = 'acknowledged'
        incident.acknowledged_by = user
        incident.acknowledged_at = timezone.now()
        incident.save()

        return Response(IncidentSerializer(incident).data)


class SafetyPostViewSet(viewsets.ModelViewSet):
    queryset = SafetyPost.objects.all().order_by('-created_at')
    serializer_class = SafetyPostSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)