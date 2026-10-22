from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from neighbour_shield_backend import settings
from math import asin, cos, radians, sin, sqrt 


# =====================================================================
# AREAS, USERS, DEVICES
# =====================================================================
class Area(models.Model):
    """A block/zone of the township. Used to target broadcasts and group reports."""
    name = models.CharField(max_length=100, unique=True)
    center_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    center_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    radius_m = models.PositiveIntegerField(null=True, blank=True)

    def __str__(self):
        return self.name
    
    @property
    def has_boundary(self):
        """True only when centre + radius are both configured."""
        return (self.center_latitude is not None
                and self.center_longitude is not None
                and self.radius_m is not None)


    # ── ADD FROM HERE ─────────────────────────────────────────────
    def distance_to(self, latitude, longitude):
        """Haversine distance from this area's centre, in metres.
        Returns None if the area has no centre or no point was supplied."""
        if (self.center_latitude is None or self.center_longitude is None
                or latitude is None or longitude is None):
            return None
        r = 6_371_000
        lat1, lon1 = radians(float(self.center_latitude)), radians(float(self.center_longitude))
        lat2, lon2 = radians(float(latitude)), radians(float(longitude))
        dlat, dlon = lat2 - lat1, lon2 - lon1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        return r * 2 * asin(sqrt(min(1.0, a)))

    def contains(self, latitude, longitude):
            """True if the point is inside the area, or if the area has no
            complete boundary. Caller should check `has_boundary` to know which."""
            if not self.has_boundary:
                return True
            if latitude is None or longitude is None:
                return True
            return self.distance_to(latitude, longitude) <= self.radius_m
    # ── ADD UNTIL HERE ────────────────────────────────────────────

class Street(models.Model):
    """A named road inside an area. Keeps address/postal data consistent."""
    area = models.ForeignKey(Area, on_delete=models.CASCADE, related_name='streets')
    name = models.CharField(max_length=150)
    postal_code = models.CharField(max_length=10, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['area__name', 'name']
        unique_together = ('area', 'name')

    def __str__(self):
        return f'{self.name} ({self.area.name})'

class Property(models.Model):
    """A residential unit registered by the township before residents are assigned."""
    PROPERTY_TYPES = (
        ('house', 'House'), ('apartment', 'Apartment / condominium'),
        ('townhouse', 'Townhouse'), ('other', 'Other'),
    )
    street = models.ForeignKey(
        Street, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='properties',
    )
    area = models.ForeignKey(Area, on_delete=models.PROTECT, related_name='properties')
    unit_number = models.CharField(max_length=100)
    address_line = models.CharField(max_length=255)
    postal_code = models.CharField(max_length=20, blank=True)
    property_type = models.CharField(max_length=20, choices=PROPERTY_TYPES, default='house')
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['area__name', 'unit_number']
        constraints = [
            models.UniqueConstraint(fields=['area', 'unit_number'], name='property_area_unit_unique'),
            models.CheckConstraint(
                condition=models.Q(latitude__isnull=True) | models.Q(latitude__gte=-90, latitude__lte=90),
                name='property_latitude_range'),
            models.CheckConstraint(
                condition=models.Q(longitude__isnull=True) | models.Q(longitude__gte=-180, longitude__lte=180),
                name='property_longitude_range'),
        ]

    def __str__(self):
        return f'{self.unit_number}, {self.address_line}'


class User(AbstractUser):
    ROLE_CHOICES = (
        ('resident', 'Resident'),
        ('volunteer', 'Volunteer Responder'),
        ('security', 'Security Personnel'),
        ('admin', 'Administrator'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='resident')
    phone_number = models.CharField(max_length=15, blank=True)
    unit_address = models.CharField(max_length=255, blank=True)
    area = models.ForeignKey('Area', null=True, blank=True,
                             on_delete=models.SET_NULL, related_name='residents')
    residence = models.ForeignKey('Property', null=True, blank=True,
                                  on_delete=models.SET_NULL, related_name='residents')

    # Volunteer programme
    is_volunteer_opted_in = models.BooleanField(default=False)    # user chooses
    is_verified_volunteer = models.BooleanField(default=False)    # admin sets
    volunteer_verified_by = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='volunteers_verified')
    volunteer_verified_at = models.DateTimeField(null=True, blank=True)

    # Last known location (SENSITIVE: never expose to other residents, never show in admin).
    # Only meaningful while fresh; see purge_stale_locations().
    last_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    last_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    last_location_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'{self.username} ({self.role})'

    def clean(self):
        super().clean()
        if self.residence_id and self.area_id and self.residence.area_id != self.area_id:
            raise ValidationError({'residence': 'The selected property belongs to a different area.'})

    # ---- helpers -----------------------------------------------------
    @property
    def is_township_admin(self):
        return self.is_active and (self.is_superuser or self.role == 'admin')

    @property
    def is_eligible_volunteer(self):
        """Verified AND opted in AND active. Check this at notify time and at ack time."""
        return self.is_active and self.is_verified_volunteer and self.is_volunteer_opted_in

    def has_fresh_location(self, max_age_minutes=10):
        if not (self.last_location_at and self.last_latitude is not None):
            return False
        return self.last_location_at >= timezone.now() - timedelta(minutes=max_age_minutes)

    @classmethod
    def purge_stale_locations(cls, max_age_minutes=10):
        """Run from a Celery beat task every few minutes. Returns rows cleared."""
        cutoff = timezone.now() - timedelta(minutes=max_age_minutes)
        return cls.objects.filter(last_location_at__lt=cutoff).update(
            last_latitude=None, last_longitude=None, last_location_at=None)

    def set_volunteer_verified(self, verified, by_user=None):
        """Single source of truth for promoting/demoting a volunteer."""
        self.is_verified_volunteer = verified
        if verified:
            self.is_volunteer_opted_in = True
            if self.role == 'resident':
                self.role = 'volunteer'  # <--- THIS WAS MISSING
            self.volunteer_verified_by = by_user
            self.volunteer_verified_at = timezone.now()
        else:
            self.volunteer_verified_by = None
            self.volunteer_verified_at = None
            if self.role == 'volunteer':
                self.role = 'resident'

class Device(models.Model):
    """One row per phone/install, so users with several devices all get pushes."""
    PLATFORM_CHOICES = (('android', 'Android'), ('ios', 'iOS'), ('web', 'Web'))

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='devices')
    fcm_token = models.CharField(max_length=255, unique=True)
    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES, default='android')
    is_active = models.BooleanField(default=True)   # set False when FCM reports the token invalid
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f'{self.user} / {self.platform}'


# =====================================================================
# SOS WORKFLOW
# =====================================================================
class EscalationPolicy(models.Model):
    """Single-row settings table (always pk=1). Edit it in the admin."""
    ack_timeout_seconds = models.PositiveIntegerField(default=60)
    volunteer_radius_m = models.PositiveIntegerField(default=500)
    max_level = models.PositiveSmallIntegerField(default=2)

    class Meta:
        verbose_name_plural = 'escalation policy'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return 'Escalation policy'


class Incident(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending Response'),
        ('acknowledged', 'Acknowledged'),
        ('escalated', 'Escalated'),
        ('resolved', 'Resolved'),
        ('cancelled', 'Cancelled / False alarm'),
    )
    TYPE_CHOICES = (
        ('medical', 'Medical'), ('crime', 'Crime / security'), ('fire', 'Fire'),
        ('accident', 'Accident'), ('other', 'Other'),
    )
    OPEN_STATUSES = ('pending', 'acknowledged', 'escalated')
    AWAITING_ACK_STATUSES = ('pending', 'escalated')

    # PROTECT: deactivate users instead of deleting them, so history survives.
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='incidents')
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    message = models.CharField(max_length=255, blank=True)
    incident_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='other', db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES,
                              default='pending', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    # Escalation (queried by the Celery beat task)
    escalation_level = models.PositiveSmallIntegerField(default=0)
    next_escalation_at = models.DateTimeField(null=True, blank=True, db_index=True)
    escalated_at = models.DateTimeField(null=True, blank=True)   # time of latest escalation

    # First acknowledgement shortcut (fast response-time analytics)
    acknowledged_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='handled_incidents')
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_incidents')
    resolution_note = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'next_escalation_at'], name='inc_status_next_esc_idx'),
            models.Index(fields=['status', 'created_at'], name='inc_status_created_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(latitude__gte=-90, latitude__lte=90),
                name='incident_latitude_range'),
            models.CheckConstraint(
                condition=models.Q(longitude__gte=-180, longitude__lte=180),
                name='incident_longitude_range'),
        ]

    def __str__(self):
        return f'SOS #{self.pk} - {self.status}'

    # ---- workflow helpers (call these from your API / Celery tasks) --------
    @classmethod
    def create_sos(cls, user, latitude, longitude, message='', incident_type='other'):
        """Create the incident, start the escalation clock and write the first log line."""
        # Local import to prevent circular dependency issues
        from .services import dispatch_sos_notifications

        policy = EscalationPolicy.get_solo()
        with transaction.atomic():
            incident = cls.objects.create(
                user=user, latitude=latitude, longitude=longitude, message=message,
                incident_type=incident_type,
                next_escalation_at=timezone.now() + timedelta(seconds=policy.ack_timeout_seconds))
            IncidentLog.objects.create(incident=incident, action='triggered', actor=user,
                                       detail='SOS triggered')

        # Trigger wave 0 notifications immediately after database commit
        dispatch_sos_notifications(incident)

        return incident

    @classmethod
    def acknowledge(cls, incident_id, responder, eta_minutes=None, note=''):
        """
        Race-safe acknowledgement. The row is locked, so two simultaneous taps
        cannot overwrite acknowledged_by. Returns (incident, ack, is_first_ack).
        """
        with transaction.atomic():
            incident = cls.objects.select_for_update().get(pk=incident_id)
            if incident.status not in cls.OPEN_STATUSES:
                raise ValidationError('This incident is already closed.')

            if responder.is_active and responder.role == 'security':
                responder_type = 'security'
            elif responder.is_eligible_volunteer:
                responder_type = 'volunteer'
            else:
                raise ValidationError('You are not an authorised responder.')

            ack, created = Acknowledgement.objects.get_or_create(
                incident=incident, responder=responder,
                defaults={'responder_type': responder_type,
                          'eta_minutes': eta_minutes, 'note': note})

            is_first = False
            if created:
                if incident.acknowledged_by_id is None:
                    is_first = True
                    incident.acknowledged_by = responder
                    incident.acknowledged_at = ack.acknowledged_at
                    incident.status = 'acknowledged'
                    incident.next_escalation_at = None      # stop the clock
                    incident.save(update_fields=['acknowledged_by', 'acknowledged_at',
                                                 'status', 'next_escalation_at'])
                IncidentLog.objects.create(
                    incident=incident, action='acknowledged', actor=responder,
                    detail=f'{responder_type} acknowledged',
                    data={'eta_minutes': eta_minutes, 'first': is_first})
            return incident, ack, is_first

    def escalate(self):
        """
        Called by Celery for incidents whose next_escalation_at has passed.
        Returns the new level, or None if nothing was escalated.
        """
        policy = EscalationPolicy.get_solo()
        with transaction.atomic():
            inc = Incident.objects.select_for_update().get(pk=self.pk)
            now = timezone.now()
            if (inc.status not in self.AWAITING_ACK_STATUSES
                    or inc.next_escalation_at is None or inc.next_escalation_at > now):
                return None

            if inc.escalation_level >= policy.max_level:
                inc.next_escalation_at = None       # top of the ladder, flag on dashboard
                inc.save(update_fields=['next_escalation_at'])
                IncidentLog.objects.create(incident=inc, action='note',
                                           detail='Max escalation level reached, still unacknowledged')
                return None

            inc.escalation_level += 1
            inc.status = 'escalated'
            inc.escalated_at = now
            inc.next_escalation_at = now + timedelta(seconds=policy.ack_timeout_seconds)
            inc.save(update_fields=['escalation_level', 'status', 'escalated_at',
                                    'next_escalation_at'])
            IncidentLog.objects.create(incident=inc, action='escalated',
                                       detail=f'Escalated to level {inc.escalation_level}',
                                       data={'level': inc.escalation_level})
            return inc.escalation_level


class Notification(models.Model):
    """Delivery tracking, SEPARATE from acknowledgement."""
    STATUS_CHOICES = (
        ('pending', 'Pending'), ('sent', 'Sent to FCM'),
        ('delivered', 'Delivered'), ('failed', 'Failed'),
    )
    AUDIENCE_CHOICES = (('security', 'Security'), ('volunteer', 'Volunteer'), ('admin', 'Admin'))

    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name='notifications')
    recipient = models.ForeignKey(User, on_delete=models.PROTECT, related_name='notifications')
    device = models.ForeignKey(Device, null=True, blank=True, on_delete=models.SET_NULL,
                               related_name='notifications')
    audience = models.CharField(max_length=20, choices=AUDIENCE_CHOICES)
    escalation_level = models.PositiveSmallIntegerField(default=0)   # 0 = first wave
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    fcm_message_id = models.CharField(max_length=255, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        indexes = [models.Index(fields=['incident', 'escalation_level'], name='notif_inc_level_idx')]

    def __str__(self):
        return f'Notif #{self.pk} -> {self.recipient} ({self.status})'


class Acknowledgement(models.Model):
    """A responder saying 'I'm on it'."""
    RESPONDER_CHOICES = (('security', 'Security'), ('volunteer', 'Volunteer'))

    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name='acknowledgements')
    responder = models.ForeignKey(User, on_delete=models.PROTECT, related_name='acknowledgements')
    # Derived from the responder in save(); never trust the client for this.
    responder_type = models.CharField(max_length=20, choices=RESPONDER_CHOICES, blank=True)
    acknowledged_at = models.DateTimeField(auto_now_add=True)
    eta_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ('incident', 'responder')
        constraints = [
            models.CheckConstraint(
                condition=models.Q(eta_minutes__isnull=True) | models.Q(eta_minutes__gt=0),
                name='ack_eta_positive'),
        ]

    def save(self, *args, **kwargs):
        self.responder_type = 'security' if self.responder.role == 'security' else 'volunteer'
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.responder} ack SOS #{self.incident_id}'


class IncidentLog(models.Model):
    """Append-only history of everything that happens to an incident."""
    ACTION_CHOICES = (
        ('triggered', 'SOS triggered'), ('notified', 'Responders notified'),
        ('acknowledged', 'Acknowledged'), ('escalated', 'Escalated'),
        ('status_changed', 'Status changed'), ('resolved', 'Resolved'),
        ('cancelled', 'Cancelled'), ('note', 'Note added'),
    )
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name='logs')
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name='incident_actions')
    detail = models.CharField(max_length=255, blank=True)
    data = models.JSONField(default=dict, blank=True)      # ETA, escalation level, etc.
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError('Incident log entries are append-only.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Incident log entries cannot be deleted.')

    def __str__(self):
        return f'#{self.incident_id} {self.action}'


# =====================================================================
# SAFETY FEED + BROADCAST
# =====================================================================
class SafetyPost(models.Model):
    POST_TYPES = (
        ('hazard', 'Resident Hazard Report'),
        ('announcement', 'Official Announcement'),
        ('broadcast', 'Emergency Broadcast'),
    )
    CATEGORY_CHOICES = (
        ('broken_light', 'Broken street light'), ('suspicious', 'Suspicious activity'),
        ('road', 'Road damage'), ('flood', 'Flooding'), ('fire', 'Fire hazard'),
        ('road_closure', 'Road closure'), ('maintenance', 'Maintenance'),
        ('other', 'Other'),
    )
    SEVERITY_CHOICES = (('info', 'Info'), ('warning', 'Warning'), ('critical', 'Critical'))
    STATUS_CHOICES = (
        ('open', 'Open'), ('in_progress', 'In progress'),
        ('resolved', 'Resolved'), ('rejected', 'Rejected'),
    )

    author = models.ForeignKey(User, on_delete=models.PROTECT, related_name='posts')
    post_type = models.CharField(max_length=20, choices=POST_TYPES, default='hazard', db_index=True)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default='other', db_index=True)
    title = models.CharField(max_length=150)
    description = models.TextField()
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    image = models.ImageField(upload_to='reports/', null=True, blank=True)   # strip EXIF GPS on upload

    # area            = where a hazard is located (used for recurring-issue analytics)
    # affected_areas  = audience of an announcement/broadcast (empty = whole township)
    area = models.ForeignKey(Area, null=True, blank=True, on_delete=models.SET_NULL,
                             related_name='posts')
    affected_areas = models.ManyToManyField(Area, blank=True, related_name='targeted_posts')
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='info')

    # Hazard lifecycle. Announcements/broadcasts are official by post_type.
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    is_verified = models.BooleanField(default=False)         # only admin may set
    verified_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name='verified_posts')
    verified_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        permissions = [
            ('send_broadcast', 'Can send emergency broadcast'),
            ('verify_post', 'Can verify hazard reports'),
        ]
        indexes = [
            models.Index(fields=['category', 'area', 'created_at'], name='post_cat_area_created_idx'),
            models.Index(fields=['post_type', 'status', 'created_at'], name='post_type_status_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(is_verified=False) | models.Q(verified_by__isnull=False),
                name='verified_requires_verifier'),
            models.CheckConstraint(
                condition=(models.Q(latitude__isnull=True) |
                           models.Q(latitude__gte=-90, latitude__lte=90)),
                name='post_latitude_range'),
            models.CheckConstraint(
                condition=(models.Q(longitude__isnull=True) |
                           models.Q(longitude__gte=-180, longitude__lte=180)),
                name='post_longitude_range'),
        ]

    @property
    def is_official(self):
        return self.post_type in ('announcement', 'broadcast')

    def clean(self):
        super().clean()
        if not self.author_id:
            return
        if self.post_type == 'broadcast':
            perm = f'{self._meta.app_label}.send_broadcast'
            if not self.author.has_perm(perm):
                raise ValidationError({'post_type': 'Only authorised administrators may send emergency broadcasts.'})
        elif self.post_type == 'announcement' and not self.author.is_township_admin:
            raise ValidationError({'post_type': 'Only administrators may publish official announcements.'})

    def __str__(self):
        return f'[{self.post_type}] {self.title}'


class BroadcastRecipient(models.Model):
    """Delivery tracking for post_type='broadcast' posts."""
    post = models.ForeignKey(SafetyPost, on_delete=models.CASCADE, related_name='recipients')
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='broadcast_receipts')
    delivered = models.BooleanField(default=False)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        unique_together = ('post', 'user')
        indexes = [models.Index(fields=['post', 'delivered'], name='bcast_post_delivered_idx')]

    def __str__(self):
        return f'{self.post_id} -> {self.user}'

class CommunityPost(models.Model):
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='community_posts')
    title = models.CharField(max_length=200)
    content = models.TextField()
    is_hidden = models.BooleanField(default=False, help_text="Admin can hide inappropriate posts")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    @property
    def like_count(self):
        return self.likes.count()

    @property
    def comment_count(self):
        return self.comments.filter(is_hidden=False).count()

    def is_liked_by(self, user):
        if not user or not user.is_authenticated:
            return False
        return self.likes.filter(user=user).exists()


class CommunityPostLike(models.Model):
    """Likes for community board posts."""
    post = models.ForeignKey(CommunityPost, on_delete=models.CASCADE, related_name='likes')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='community_post_likes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('post', 'user')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} likes {self.post.title}"


class CommunityPostComment(models.Model):
    """Comments on community board posts."""
    post = models.ForeignKey(CommunityPost, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='community_post_comments')
    content = models.TextField()
    is_hidden = models.BooleanField(default=False, help_text="Admin can hide inappropriate comments")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Comment by {self.author.username} on {self.post.title}"

