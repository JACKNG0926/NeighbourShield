from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Incident, User


class Command(BaseCommand):
    help = 'Escalate overdue SOS incidents and purge stale responder locations.'

    def handle(self, *args, **options):
        overdue = Incident.objects.filter(
            status__in=Incident.AWAITING_ACK_STATUSES,
            next_escalation_at__lte=timezone.now(),
        )
        escalated = sum(incident.escalate() is not None for incident in overdue)
        locations_cleared = User.purge_stale_locations()
        self.stdout.write(self.style.SUCCESS(
            f'Escalated {escalated} incident(s); cleared {locations_cleared} stale location(s).'
        ))
