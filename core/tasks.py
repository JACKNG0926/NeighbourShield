import logging

from celery import shared_task
from django.utils import timezone

from .models import Incident, User

logger = logging.getLogger(__name__)


@shared_task
def escalate_overdue_incidents():
    """Runs every 15 s from Celery beat. Replaces the manual run_escalation script."""
    from .services import dispatch_sos_notifications

    due = Incident.objects.filter(
        status__in=Incident.AWAITING_ACK_STATUSES,
        next_escalation_at__isnull=False,
        next_escalation_at__lte=timezone.now(),
    )
    escalated = 0
    for incident in due:
        try:
            level = incident.escalate()  # row-locked; returns None if nothing changed
            if level:
                incident.refresh_from_db()
                dispatch_sos_notifications(incident)
                escalated += 1
        except Exception:
            logger.exception('Escalation failed for SOS #%s', incident.pk)
    return escalated


@shared_task
def purge_stale_locations():
    """Clears volunteer last-known locations older than 10 minutes (privacy)."""
    return User.purge_stale_locations()
