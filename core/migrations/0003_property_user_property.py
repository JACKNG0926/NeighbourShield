# Generated manually to add the township property register.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_acknowledgement_area_broadcastrecipient_device_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Property',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('unit_number', models.CharField(max_length=100)),
                ('address_line', models.CharField(max_length=255)),
                ('postal_code', models.CharField(blank=True, max_length=20)),
                ('property_type', models.CharField(choices=[('house', 'House'), ('apartment', 'Apartment / condominium'), ('townhouse', 'Townhouse'), ('other', 'Other')], default='house', max_length=20)),
                ('latitude', models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ('longitude', models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('area', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='properties', to='core.area')),
            ],
            options={'ordering': ['area__name', 'unit_number']},
        ),
        migrations.AddConstraint(
            model_name='property',
            constraint=models.UniqueConstraint(fields=('area', 'unit_number'), name='property_area_unit_unique'),
        ),
        migrations.AddConstraint(
            model_name='property',
            constraint=models.CheckConstraint(condition=models.Q(('latitude__isnull', True), models.Q(('latitude__gte', -90), ('latitude__lte', 90)), _connector='OR'), name='property_latitude_range'),
        ),
        migrations.AddConstraint(
            model_name='property',
            constraint=models.CheckConstraint(condition=models.Q(('longitude__isnull', True), models.Q(('longitude__gte', -180), ('longitude__lte', 180)), _connector='OR'), name='property_longitude_range'),
        ),
        migrations.AddField(
            model_name='user',
            name='residence',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='residents', to='core.property'),
        ),
    ]
