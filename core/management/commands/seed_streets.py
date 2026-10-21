from django.core.management.base import BaseCommand
from core.models import Property, Street


class Command(BaseCommand):
    help = 'Create a Street row for every existing Property.address_line.'

    def handle(self, *args, **options):
        pending = Property.objects.filter(street__isnull=True)
        total = pending.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS(
                'Nothing to seed - all properties already have a street.'
            ))
            return

        created_streets = 0
        linked = 0
        for p in pending:
            street, was_created = Street.objects.get_or_create(
                area=p.area,
                name=p.address_line,
                defaults={'postal_code': p.postal_code or ''},
            )
            if was_created:
                created_streets += 1
            p.street = street
            p.save(update_fields=['street'])
            linked += 1

        self.stdout.write(self.style.SUCCESS(
            f'Linked {linked}/{total} properties. '
            f'{created_streets} new Street rows created.'
        ))
