from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    ROLE_CHOICES = (
        ('resident', 'Resident'),
        ('volunteer', 'Volunteer Responder'),
        ('security', 'Security Personnel'),
        ('admin', 'Administrator'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='resident')
    phone_number = models.CharField(max_length=15, blank=True)
    is_volunteer_opted_in = models.BooleanField(default=False)
    fcm_token = models.CharField(max_length=255, blank=True, null=True)

class Incident(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending Response'),
        ('acknowledged', 'Acknowledged'),
        ('escalated', 'Escalated'),
        ('resolved', 'Resolved'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='incidents')
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    acknowledged_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='handled_incidents'
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)

class SafetyPost(models.Model):
    POST_TYPES = (
        ('hazard', 'Resident Hazard Report'),
        ('announcement', 'Official Announcement'),
        ('broadcast', 'Emergency Broadcast'),
    )
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    post_type = models.CharField(max_length=20, choices=POST_TYPES, default='hazard')
    title = models.CharField(max_length=150)
    description = models.TextField()
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    image = models.ImageField(upload_to='reports/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)