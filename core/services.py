from django.utils import timezone
from .models import Device, Notification, EscalationPolicy, User


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