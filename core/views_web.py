import json
from django.contrib import messages
from django.shortcuts import redirect, render
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Count
from .forms import AreaRegistrationForm, PropertyRegistrationForm
from .models import Area, Incident, Property


township_admin_required = user_passes_test(
    lambda user: user.is_authenticated and user.is_township_admin,
    login_url='/admin/login/',
)


@township_admin_required
def admin_dashboard(request):
    # This view is read-only. Area/property registration lives at /township/.
    return _dashboard_context(request)


@township_admin_required
def township_management(request):
    area_form = AreaRegistrationForm(prefix='area')
    property_form = PropertyRegistrationForm(prefix='property')

    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        if form_type == 'area':
            area_form = AreaRegistrationForm(request.POST, prefix='area')
            if area_form.is_valid():
                area = area_form.save()
                messages.success(request, f'Area "{area.name}" was added.')
                return redirect('township-management')
        elif form_type == 'property':
            property_form = PropertyRegistrationForm(request.POST, prefix='property')
            if property_form.is_valid():
                registered_property = property_form.save()
                messages.success(request, f'Property "{registered_property}" was added.')
                return redirect('township-management')

    return render(request, 'core/township_management.html', {
        'area_form': area_form,
        'property_form': property_form,
    })


def _dashboard_context(request):
    # Fetch recent pending and acknowledged incidents
    incidents = Incident.objects.exclude(status='resolved').order_by('-created_at')

    # Create a list of dictionaries for the map markers
    map_markers = []
    for incident in incidents:
        map_markers.append({
            'user': incident.user.username,
            'lat': float(incident.latitude),
            'lng': float(incident.longitude),
            'status': incident.status,
            'time': incident.created_at.strftime("%b %d, %Y %H:%M")
        })

    property_markers = [
        {
            'unit_number': registered_property.unit_number,
            'address': registered_property.address_line,
            'area': registered_property.area.name,
            'lat': float(registered_property.latitude),
            'lng': float(registered_property.longitude),
            'resident_count': registered_property.resident_total,
        }
        for registered_property in Property.objects.select_related('area').annotate(
            resident_total=Count('residents')
        ).filter(
            is_active=True, latitude__isnull=False, longitude__isnull=False
        )
    ]

    area_boundaries = [
        {
            'name': area.name,
            'lat': float(area.center_latitude),
            'lng': float(area.center_longitude),
            'radius_m': area.radius_m,
        }
        for area in Area.objects.filter(
            center_latitude__isnull=False,
            center_longitude__isnull=False,
            radius_m__isnull=False,
        )
    ]

    context = {
        'incidents': incidents,
        'map_markers_json': json.dumps(map_markers),  # Pass JSON to the template
        'property_markers_json': json.dumps(property_markers),
        'area_boundaries_json': json.dumps(area_boundaries),
    }
    return render(request, 'core/dashboard.html', context)
