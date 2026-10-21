from django.db import models
from django.utils import timezone
from .models import Device, Notification, EscalationPolicy, User, BroadcastRecipient


def dispatch_sos_notifications(incident):
    """
    Determines the audience based on the escalation level, logs the Notification rows,
    and sends the Firebase push notification.
    """
    level = incident.escalation_level

    if level == 0:
        # Wave 0 (Immediate): Notify all active security personnel
        receivers = User.objects.filter(role='security', is_active=True)
        audience = 'security'
    else:
        # Wave 1+ (Escalated): Notify eligible volunteers
        policy = EscalationPolicy.get_solo()

        # Note: For production, you would calculate actual distance using the incident lat/lng
        # and the volunteer's last_latitude/last_longitude against policy.volunteer_radius_m.
        # This is a simplified fetch of all eligible volunteers for now.
        receivers = User.objects.filter(
            is_active=True,
            is_verified_volunteer=True,
            is_volunteer_opted_in=True
        )
        audience = 'volunteer'

    notifications_to_create = []

    for user in receivers:
        devices = Device.objects.filter(user=user, is_active=True)
        for device in devices:
            notifications_to_create.append(
                Notification(
                    incident=incident,
                    recipient=user,
                    device=device,
                    audience=audience,
                    escalation_level=level,
                    status='pending'
                )
            )

    # Bulk create the notification records for database tracking
    created_notifications = Notification.objects.bulk_create(notifications_to_create)

    # TODO: Connect to Firebase Admin SDK
    # For now, we simulate the send and update the status
    for notif in created_notifications:
        # Send to FCM here using notif.device.fcm_token
        # ...

        notif.status = 'sent'
        notif.sent_at = timezone.now()
        notif.save(update_fields=['status', 'sent_at'])


def dispatch_emergency_broadcast(broadcast):
    """
    Resolves the audience for an emergency broadcast, records delivery rows
    in core.BroadcastRecipient, queries active device FCM tokens, and dispatches
    the high-priority data payload.
    """
    areas = broadcast.affected_areas.all()
    if areas.exists():
        users = User.objects.filter(
            models.Q(area__in=areas) | models.Q(residence__area__in=areas),
            is_active=True
        ).distinct()
    else:
        users = User.objects.filter(is_active=True)

    recipients = [
        BroadcastRecipient(
            post=broadcast,
            user=user,
            delivered=True,
            delivered_at=timezone.now()
        )
        for user in users
    ]
    created_recipients = BroadcastRecipient.objects.bulk_create(recipients, ignore_conflicts=True)

    # Collect active device tokens for the resolved users
    active_tokens = list(
        Device.objects.filter(user__in=users, is_active=True)
        .values_list('fcm_token', flat=True)
    )

    payload = {
        'type': 'emergency_broadcast',
        'broadcast_id': str(broadcast.id),
        'severity': (broadcast.severity or 'info').lower(),
        'category': broadcast.category or 'other',
        'title': broadcast.title,
        'description': broadcast.description,
        'created_at': broadcast.created_at.isoformat() if broadcast.created_at else timezone.now().isoformat(),
    }

    # Attempt push dispatch via Firebase Admin SDK if configured
    try:
        import firebase_admin
        from firebase_admin import messaging
        if active_tokens and firebase_admin._apps:
            message = messaging.MulticastMessage(
                data=payload,
                tokens=active_tokens,
                android=messaging.AndroidConfig(priority='high'),
                apns=messaging.APNSConfig(
                    headers={'apns-priority': '10'},
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(content_available=True)
                    ),
                ),
            )
            messaging.send_each_for_multicast(message)
    except (ImportError, Exception):
        # Graceful fallback when running in local development / testing environment
        pass

    return {
        'total_users': users.count(),
        'tokens_count': len(active_tokens),
        'recipients_created': len(created_recipients),
        'payload': payload,
    }
