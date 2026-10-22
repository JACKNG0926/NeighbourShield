import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import models, transaction
from django.contrib.auth import authenticate
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from math import asin, cos, radians, sin, sqrt
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated, SAFE_METHODS
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.authtoken.models import Token
from django.core.exceptions import ValidationError as DjangoValidationError
from .models import Area, Device, Property, User, Incident, IncidentLog, SafetyPost, EscalationPolicy, CommunityPost, CommunityPostLike, CommunityPostComment
from .permissions import IsTownshipAdmin
from .serializers import (AreaSerializer, ChangePasswordSerializer, DeviceSerializer, LocationUpdateSerializer,
                          MobileProfileSerializer, PropertySerializer, RegistrationSerializer,
                          UserSerializer, IncidentSerializer, SafetyPostSerializer, CommunityPostSerializer, CommunityPostCommentSerializer)


logger = logging.getLogger(__name__)


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

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fcm_token = serializer.validated_data['fcm_token']
        platform = serializer.validated_data.get('platform', 'android')
        is_active = serializer.validated_data.get('is_active', True)

        device, created = Device.objects.update_or_create(
            fcm_token=fcm_token,
            defaults={
                'user': request.user,
                'platform': platform,
                'is_active': is_active,
                'last_seen': timezone.now(),
            }
        )
        output_serializer = self.get_serializer(device)
        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(output_serializer.data, status=status_code)


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
        data = dict(serializer.validated_data)
        user = request.user
        incident_type = data.get('incident_type', 'other')

        if incident_type == 'backup':
            # Only responders may ask for backup, and only one open request at a time.
            if not (user.is_active and (user.role == 'security' or user.is_eligible_volunteer)):
                return Response({'detail': 'Only responders can request backup.'},
                                status=status.HTTP_403_FORBIDDEN)
            if Incident.objects.filter(user=user, incident_type='backup',
                                       status__in=Incident.OPEN_STATUSES).exists():
                return Response({'detail': 'You already have an active backup request.'},
                                status=status.HTTP_400_BAD_REQUEST)
            if not data.get('contact_phone'):
                data['contact_phone'] = (user.phone_number or '')[:20]
        else:
            # Server-side fallback so responders always get the resident's phone and
            # unit address, even if the client did not send them.
            if not data.get('contact_phone'):
                data['contact_phone'] = (user.phone_number or '')[:20]
            if not data.get('location_notes'):
                data['location_notes'] = (user.unit_address or '')[:255]

        incident = Incident.create_sos(user=user, **data)
        return Response(self.get_serializer(incident).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        user = request.user
        if not (user.is_township_admin or (user.is_active and user.role == 'security')):
            return Response({'detail': 'Only security or administrators can resolve incidents.'},
                            status=status.HTTP_403_FORBIDDEN)
        note = str(request.data.get('note', '') or '')[:2000]
        with transaction.atomic():
            incident = Incident.objects.select_for_update().get(pk=self.get_object().pk)
            if incident.status in ('resolved', 'cancelled'):
                return Response({'detail': 'This incident is already closed.'},
                                status=status.HTTP_400_BAD_REQUEST)
            incident.status = 'resolved'
            incident.resolved_at = timezone.now()
            incident.resolved_by = user
            incident.resolution_note = note
            incident.next_escalation_at = None
            incident.save(update_fields=['status', 'resolved_at', 'resolved_by',
                                         'resolution_note', 'next_escalation_at'])
            IncidentLog.objects.create(incident=incident, action='resolved', actor=user,
                                       detail='Resolved', data={'note': note})
        return Response(self.get_serializer(incident).data)

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
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        if self.action in ('list', 'retrieve') or self.request.user.is_township_admin:
            return SafetyPost.objects.all().order_by('-created_at')
        return SafetyPost.objects.filter(author=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    @action(detail=False, methods=['get'], url_path='latest_broadcast')
    def latest_broadcast(self, request):
        """
        Returns the latest open emergency broadcast for local development real-time synchronization.
        Resolves audience based on user area or township-wide broadcasts.
        """
        user = request.user
        broadcasts = SafetyPost.active_broadcasts()  # open AND not expired
        user_area = getattr(user, 'area', None) or getattr(getattr(user, 'residence', None), 'area', None)
        if user_area:
            broadcasts = broadcasts.filter(
                models.Q(affected_areas=user_area) | models.Q(affected_areas__isnull=True)
            ).distinct()

        latest = broadcasts.order_by('-created_at').first()
        if not latest:
            return Response({'broadcast': None})

        return Response({
            'broadcast': {
                'id': latest.id,
                'broadcast_id': str(latest.id),
                'title': latest.title,
                'description': latest.description,
                'severity': (latest.severity or 'info').lower(),
                'category': latest.category or 'other',
                'status': latest.status,
                'created_at': latest.created_at.isoformat() if latest.created_at else None,
            }
        })


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

class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data['new_password'])
        user.save(update_fields=['password'])
        # Rotate the token so any old sessions stop working; the app stores the new one.
        Token.objects.filter(user=user).delete()
        token = Token.objects.create(user=user)
        return Response({'token': token.key, 'detail': 'Password changed.'})


class PasswordResetRequestView(APIView):
    """Emails a reset link. The link opens Django's built-in reset page
    (django.contrib.auth.urls mounted at /accounts/)."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'password_reset'

    def post(self, request):
        email = str(request.data.get('email', '') or '').strip()
        if not email or '@' not in email:
            return Response({'detail': 'Enter a valid email address.'},
                            status=status.HTTP_400_BAD_REQUEST)

        for user in User.objects.filter(email__iexact=email, is_active=True):
            if not user.has_usable_password():
                continue
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            link = f"{settings.SITE_URL.rstrip('/')}/accounts/reset/{uid}/{token}/"
            try:
                send_mail(
                    subject='NeighbourShield password reset',
                    message=(f'Hi {user.username},\n\nUse this link to choose a new password:\n'
                             f'{link}\n\nIf you did not request this, ignore this email.'),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
            except Exception:
                logger.exception('Could not send password reset email to user %s', user.pk)

        # Same answer whether or not the account exists (prevents email enumeration).
        return Response({'detail': 'If an account with that email exists, a reset link has been sent.'})


class CommunityPostViewSet(viewsets.ModelViewSet):
    queryset = CommunityPost.objects.all().order_by('-created_at')
    serializer_class = CommunityPostSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        user = self.request.user
        if getattr(user, 'is_township_admin', False) or user.is_staff or user.is_superuser:
            return CommunityPost.objects.all().order_by('-created_at')
        return CommunityPost.objects.filter(is_hidden=False).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def like(self, request, pk=None):
        post = self.get_object()
        existing_like = CommunityPostLike.objects.filter(post=post, user=request.user)
        if existing_like.exists():
            existing_like.delete()
            is_liked = False
        else:
            CommunityPostLike.objects.create(post=post, user=request.user)
            is_liked = True
        return Response({
            'is_liked': is_liked,
            'likes_count': post.likes.count(),
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get', 'post'], permission_classes=[IsAuthenticated])
    def comments(self, request, pk=None):
        post = self.get_object()
        if request.method == 'GET':
            comments = post.comments.filter(is_hidden=False).select_related('author').order_by('created_at')
            serializer = CommunityPostCommentSerializer(comments, many=True, context={'request': request})
            return Response(serializer.data, status=status.HTTP_200_OK)

        content = request.data.get('content', '').strip()
        if not content:
            return Response({'detail': 'Comment content cannot be empty.'}, status=status.HTTP_400_BAD_REQUEST)

        comment = CommunityPostComment.objects.create(
            post=post,
            author=request.user,
            content=content,
        )
        serializer = CommunityPostCommentSerializer(comment, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

