import json
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import Incident, SafetyPost


@login_required(login_url='/admin/login/')
def admin_dashboard(request):
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

    context = {
        'incidents': incidents,
        'map_markers_json': json.dumps(map_markers),  # Pass JSON to the template
    }
    return render(request, 'core/dashboard.html', context)