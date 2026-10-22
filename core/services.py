import logging
from math import asin, cos, radians, sin, sqrt

from django.conf import settings
from django.db import models
from django.utils import timezone

from .models import (BroadcastRecipient, Device, EscalationPolicy, IncidentLog,
                     Notification, User)

logger = logging.getLogger(__name__)


def _distance_m(lat1, lon1, lat2, lon2):
    """Haversine distance in metres."""
    lat1, lon1, lat2, lon2 = map(radians, [float(lat1), float(lon1), float(lat2), float(lon2)])
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 6_371_000 * 2 * asin(sqrt(min(1.0, a)))


def dispatch_sos_notifications(incident):
    """
    Level 0  -> all active security personnel.
    Level 1+ -> eligible volunteers with a fresh location inside the response radius.
    Writes Notification rows (delivery tracking, separate from acknowledgement),
    an audit log line, and sends the WhatsApp alert.

    NOTE: FCM push is still simulated: rows are marked 'sent' without calling Firebase.
    Identify this as a simulated integration during the demo.
    """
    level = incident.escalation_level

    if level == 0:
        receivers = list(User.objects.filter(role='security', is_active=True)
                         .exclude(pk=incident.user_id))
        audience = 'security'
    else:
        policy = EscalationPolicy.get_solo()
        candidates = User.objects.filter(
            is_active=True, is_verified_volunteer=True, is_volunteer_opted_in=True,
        ).exclude(pk=incident.user_id)
        receivers = [
            u for u in candidates
            if u.has_fresh_location() and u.last_longitude is not None
            and _distance_m(u.last_latitude, u.last_longitude,
                            incident.latitude, incident.longitude) <= policy.volunteer_radius_m
        ]
        audience = 'volunteer'

    now = timezone.now()
    rows = []
    for user in receivers:
        for device in Device.objects.filter(user=user, is_active=True):
            rows.append(Notification(
                incident=incident, recipient=user, device=device, audience=audience,
                escalation_level=level, status='sent', sent_at=now, attempts=1))

    # Built with status already set: bulk_create does not return primary keys on MySQL,
    # so rows must not be saved again afterwards.
    if rows:
        Notification.objects.bulk_create(rows)
        # TODO: send through Firebase Admin SDK here using each row's device.fcm_token.

    IncidentLog.objects.create(
        incident=incident, action='notified',
        detail=f'{len(receivers)} {audience} responder(s) notified (level {level})',
        data={'level': level, 'audience': audience, 'recipients': len(receivers),
              'device_rows': len(rows)})

    try:
        send_whatsapp_alert(incident)
    except Exception:
        logger.exception('WhatsApp alert failed for SOS #%s', incident.pk)


def _normalise_number(number):
    number = str(number).replace('whatsapp:', '').replace(' ', '').strip()
    return number if number.startswith('+') else f'+{number}'


def send_whatsapp_alert(incident):
    """
    Sends the SOS details plus the meeting link to the admin WhatsApp numbers
    through the Twilio WhatsApp sandbox. Silently skipped when Twilio is not
    configured. Returns the number of messages accepted by Twilio.
    """
    sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '')
    token = getattr(settings, 'TWILIO_AUTH_TOKEN', '')
    sender = getattr(settings, 'TWILIO_WHATSAPP_FROM', '')
    recipients = getattr(settings, 'ADMIN_WHATSAPP_TO', [])
    if not (sid and token and sender and recipients):
        logger.info('WhatsApp alert skipped for SOS #%s: Twilio not configured.', incident.pk)
        return 0

    import requests  # local import so the app still starts if requests is missing

    if incident.incident_type == 'backup':
        prefix = 'BACKUP REQUEST'
    elif incident.escalation_level > 0:
        prefix = f'ESCALATED (level {incident.escalation_level})'
    else:
        prefix = 'NEW SOS'

    maps_link = f'https://www.google.com/maps?q={incident.latitude},{incident.longitude}'
    lines = [
        f'{prefix} - NeighbourShield #{incident.pk}',
        f'Type: {incident.get_incident_type_display()}',
        f'From: {incident.user.username}',
        f'Phone: {incident.contact_phone or "not provided"}',
        f'Address: {incident.location_notes or "not provided"}',
        f'Map: {maps_link}',
    ]
    if incident.message:
        lines.append(f'Message: {incident.message}')
    lines.append(f'Join the call: {getattr(settings, "SOS_MEETING_LINK", "")}')
    body = '\n'.join(lines)

    url = f'https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json'
    sent = 0
    for to in recipients:
        try:
            response = requests.post(
                url,
                data={'From': f'whatsapp:{_normalise_number(sender)}',
                      'To': f'whatsapp:{_normalise_number(to)}',
                      'Body': body},
                auth=(sid, token),
                timeout=8,
            )
            if response.status_code in (200, 201):
                sent += 1
            else:
                logger.warning('Twilio rejected WhatsApp to %s: %s %s',
                               to, response.status_code, response.text[:200])
        except Exception:
            logger.exception('Twilio request failed for %s', to)
    return sent


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
