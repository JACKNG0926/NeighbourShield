from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import Incident, SafetyPost


@login_required(login_url='/admin/login/')
def admin_dashboard(request):
    # Fetch recent pending and acknowledged incidents
    incidents = Incident.objects.exclude(status='resolved').order_by('-created_at')

    context = {
        'incidents': incidents,
    }
    return render(request, 'core/dashboard.html', context)