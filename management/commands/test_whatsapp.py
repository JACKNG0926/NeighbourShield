from types import SimpleNamespace

from django.core.management.base import BaseCommand

from core.services import send_whatsapp_alert


class Command(BaseCommand):
    help = 'Sends a fake SOS WhatsApp (with the meeting link) to check your Twilio setup.'

    def handle(self, *args, **options):
        fake = SimpleNamespace(
            pk=0, incident_type='other', escalation_level=0, latitude=3.139, longitude=101.6869,
            contact_phone='0123456789', location_notes='Test unit', message='This is a test',
            user=SimpleNamespace(username='test-user'),
            get_incident_type_display=lambda: 'Other',
        )
        sent = send_whatsapp_alert(fake)
        self.stdout.write(self.style.SUCCESS(f'{sent} message(s) accepted by Twilio.') if sent
                          else self.style.WARNING('Nothing sent: check TWILIO_* / ADMIN_WHATSAPP_TO env vars and the console log.'))
