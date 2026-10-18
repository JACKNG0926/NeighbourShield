import time
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import Incident, User


class Command(BaseCommand):
    help = 'Runs the continuous SOS escalation and location cleanup engine'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting NeighbourShield escalation engine..."))

        try:
            while True:
                # 1. Find and escalate overdue incidents
                overdue_incidents = Incident.objects.filter(
                    status__in=['pending', 'escalated'],
                    next_escalation_at__lte=timezone.now()
                )

                for incident in overdue_incidents:
                    new_level = incident.escalate()
                    if new_level:
                        self.stdout.write(f"[{timezone.now()}] Escalated Incident #{incident.pk} to level {new_level}")
                        # Trigger dispatch for the new level (implemented in step 2)
                        # dispatch_sos_notifications(incident)

                # 2. Purge stale user locations (older than 10 minutes)
                cleared_count = User.purge_stale_locations(max_age_minutes=10)
                if cleared_count > 0:
                    self.stdout.write(f"[{timezone.now()}] Purged stale locations for {cleared_count} users")

                # Sleep for 15 seconds before the next check
                time.sleep(15)

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nEscalation engine stopped by user."))