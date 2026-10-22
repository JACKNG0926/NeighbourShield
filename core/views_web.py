import json
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Count, Prefetch, Q
from django.utils import timezone
from .forms import AreaRegistrationForm, PropertyRegistrationForm, BroadcastForm
from .models import Area, Incident, Property, SafetyPost, CommunityPost, User, Street

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
    tab = request.GET.get('tab', 'area')
    area_form = AreaRegistrationForm(prefix='area')
    property_form = PropertyRegistrationForm(prefix='property')

    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        if form_type == 'area':
            tab = 'area'
            area_form = AreaRegistrationForm(request.POST, prefix='area')
            if area_form.is_valid():
                area = area_form.save()
                messages.success(request, f'Area "{area.name}" was added.')
                return redirect(f'{request.path}?tab=area')
            messages.error(request, 'Area was NOT added. See the errors below.')
        elif form_type == 'property':
            tab = 'property'
            property_form = PropertyRegistrationForm(request.POST, prefix='property')
            if property_form.is_valid():
                prop = property_form.save()
                warning = getattr(property_form, '_boundary_warning', None)
                if warning:
                    messages.warning(request, f'Property "{prop}" was added. {warning}')
                else:
                    messages.success(request, f'Property "{prop}" was added inside "{prop.area.name}".')
                return redirect(f'{request.path}?tab=property')
            messages.error(request, 'Property was NOT added. See the errors below.')

    streets_data = list(
        Street.objects.filter(is_active=True)
        .values('id', 'name', 'postal_code', 'area_id')
    )
    # Map markers for the Leaflet preview
    property_markers = [
        {'unit': p.unit_number, 'address': p.address_line, 'area': p.area.name,
         'lat': float(p.latitude), 'lng': float(p.longitude),
         'resident_count': p.resident_count}
        for p in Property.objects.select_related('area')
            .annotate(resident_count=Count('residents'))
            .filter(is_active=True, latitude__isnull=False, longitude__isnull=False)
    ]
    area_boundaries = [
        {'name': a.name, 'lat': float(a.center_latitude),
         'lng': float(a.center_longitude), 'radius_m': a.radius_m}
        for a in Area.objects.filter(
            center_latitude__isnull=False,
            center_longitude__isnull=False,
            radius_m__isnull=False,
        )
    ]

    return render(request, 'core/township_management.html', {
        'area_form': area_form,
        'property_form': property_form,
        'active_tab': tab,
        'streets_json': streets_data,
        'property_markers_json': property_markers,
        'area_boundaries_json': area_boundaries,
    })
@township_admin_required
def emergency_broadcast(request):
    if request.method == 'POST':
        form = BroadcastForm(request.POST)
        if form.is_valid():
            broadcast = form.save(commit=False)
            broadcast.author = request.user
            broadcast.post_type = 'broadcast'
            broadcast.status = 'open'
            broadcast.save()
            form.save_m2m()  # Required to save the ManyToMany affected_areas field

            from .services import dispatch_emergency_broadcast
            dispatch_stats = dispatch_emergency_broadcast(broadcast)

            messages.success(
                request,
                f'Emergency broadcast "{broadcast.title}" was dispatched to {dispatch_stats["total_users"]} resident(s) ({broadcast.severity.upper()}).'
            )
            return redirect('emergency-broadcast')
    else:
        form = BroadcastForm()

    recent_broadcasts = SafetyPost.objects.filter(post_type='broadcast').order_by('-created_at')[:10]

    return render(request, 'core/broadcast.html', {
        'form': form,
        'recent_broadcasts': recent_broadcasts,
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


@township_admin_required
def volunteer_applications(request):
    if request.method == 'POST':
        user_id = request.POST.get('user_id')

        user = get_object_or_404(
            User,
            id=user_id,
            role='resident',
            is_volunteer_opted_in=True,
            is_verified_volunteer=False,
        )
        user.set_volunteer_verified(True, request.user)
        user.save(update_fields=['role', 'is_verified_volunteer', 'is_volunteer_opted_in', 'volunteer_verified_by', 'volunteer_verified_at'])
        
        messages.success(request, f'Approved {user.username} as a volunteer.')
        return redirect('volunteer_applications')

        # Admin verifies the volunteer application.
        user.role = 'volunteer'
        user.is_verified_volunteer = True
        user.volunteer_verified_by = request.user
        user.volunteer_verified_at = timezone.now()

        user.save(
            update_fields=[
                'role',
                'is_verified_volunteer',
                'volunteer_verified_by',
                'volunteer_verified_at',
            ]
        )

        messages.success(
            request,
            f'Approved {user.username} as a volunteer.'
        )

        return redirect('volunteer_applications')

    pending_applications = User.objects.filter(
        role='resident',
        is_volunteer_opted_in=True,
        is_verified_volunteer=False,
    )

    return render(
        request,
        'core/volunteer_applications.html',
        {
            'pending_applications': pending_applications,
        },
    )

@township_admin_required
def community_board(request):
    if request.method == 'POST':
        action = request.POST.get('action')

        # 1. Handle Admin creating a new post
        if action == 'create':
            title = request.POST.get('title')
            content = request.POST.get('content')
            if title and content:
                CommunityPost.objects.create(
                    author=request.user,
                    title=title,
                    content=content,
                    is_hidden=False
                )
                messages.success(request, 'Your post has been published to the community board.')

        # 2. Handle Admin moderating (hiding/showing) existing posts
        elif action in ['hide', 'show']:
            post_id = request.POST.get('post_id')
            if post_id:
                post = CommunityPost.objects.get(id=post_id)
                post.is_hidden = (action == 'hide')
                post.save(update_fields=['is_hidden'])

                status_msg = "hidden from" if post.is_hidden else "visible to"
                messages.success(request, f'Post "{post.title}" is now {status_msg} residents.')

        return redirect('community_board')

    # Fetch all posts for the feed
    posts = CommunityPost.objects.select_related('author').all().order_by('-created_at')

    return render(request, 'core/community_board.html', {
        'posts': posts
    })


@township_admin_required
def safety_reports(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        report_id = request.POST.get('report_id')

        if report_id:
            report = get_object_or_404(SafetyPost, id=report_id, post_type='hazard')

            if action == 'update_status':
                new_status = request.POST.get('status')
                valid_statuses = [choice[0] for choice in SafetyPost.STATUS_CHOICES]
                if new_status in valid_statuses:
                    report.status = new_status
                    if new_status == 'resolved':
                        report.resolved_at = timezone.now()
                    elif report.resolved_at:
                        report.resolved_at = None
                    report.save(update_fields=['status', 'resolved_at'])
                    messages.success(request, f'Report #{report.id} "{report.title}" status updated to {report.get_status_display()}.')

            elif action == 'verify':
                report.is_verified = True
                report.verified_by = request.user
                report.verified_at = timezone.now()
                report.save(update_fields=['is_verified', 'verified_by', 'verified_at'])
                messages.success(request, f'Report #{report.id} "{report.title}" has been verified.')

            elif action == 'unverify':
                report.is_verified = False
                report.verified_by = None
                report.verified_at = None
                report.save(update_fields=['is_verified', 'verified_by', 'verified_at'])
                messages.info(request, f'Report #{report.id} verification status removed.')

            elif action == 'delete':
                title = report.title
                report.delete()
                messages.warning(request, f'Report "{title}" was removed.')

        # Preserve query params on reload
        query_params = request.GET.urlencode()
        redirect_target = f"{request.path}?{query_params}" if query_params else request.path
        return redirect(redirect_target)

    # Base query for hazard reports submitted from resident & volunteer mobile apps
    base_qs = SafetyPost.objects.filter(post_type='hazard').select_related(
        'author', 'author__area', 'author__residence', 'area', 'verified_by'
    ).order_by('-created_at')

    # KPI Statistics
    stats = {
        'total': base_qs.count(),
        'open': base_qs.filter(status='open').count(),
        'in_progress': base_qs.filter(status='in_progress').count(),
        'resolved': base_qs.filter(status='resolved').count(),
        'critical': base_qs.filter(severity='critical').count(),
        'verified': base_qs.filter(is_verified=True).count(),
        'volunteer_reports': base_qs.filter(Q(author__role='volunteer') | Q(author__is_verified_volunteer=True)).count(),
        'resident_reports': base_qs.filter(author__role='resident', author__is_verified_volunteer=False).count(),
    }

    # Filters
    reports = base_qs

    status_filter = request.GET.get('status', '').strip()
    if status_filter and status_filter != 'all':
        reports = reports.filter(status=status_filter)

    severity_filter = request.GET.get('severity', '').strip()
    if severity_filter and severity_filter != 'all':
        reports = reports.filter(severity=severity_filter)

    category_filter = request.GET.get('category', '').strip()
    if category_filter and category_filter != 'all':
        reports = reports.filter(category=category_filter)

    role_filter = request.GET.get('role', '').strip()
    if role_filter == 'volunteer':
        reports = reports.filter(Q(author__role='volunteer') | Q(author__is_verified_volunteer=True))
    elif role_filter == 'resident':
        reports = reports.filter(author__role='resident', author__is_verified_volunteer=False)

    search_query = request.GET.get('q', '').strip()
    if search_query:
        reports = reports.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(author__username__icontains=search_query) |
            Q(author__unit_address__icontains=search_query)
        )

    # Map markers for reports with coordinates
    map_markers = []
    for rep in reports:
        if rep.latitude is not None and rep.longitude is not None:
            map_markers.append({
                'id': rep.id,
                'title': rep.title,
                'category': rep.get_category_display(),
                'severity': rep.severity,
                'status': rep.status,
                'status_label': rep.get_status_display(),
                'author': rep.author.username,
                'role': 'Volunteer Responder' if (rep.author.role == 'volunteer' or rep.author.is_verified_volunteer) else 'Resident',
                'lat': float(rep.latitude),
                'lng': float(rep.longitude),
                'time': rep.created_at.strftime("%b %d, %Y %H:%M"),
            })

    # Area boundaries for township context (matching dashboard map)
    area_boundaries = [
        {
            'name': a.name,
            'lat': float(a.center_latitude),
            'lng': float(a.center_longitude),
            'radius_m': a.radius_m,
        }
        for a in Area.objects.filter(
            center_latitude__isnull=False,
            center_longitude__isnull=False,
            radius_m__isnull=False,
        )
    ]

    return render(request, 'core/safety_reports.html', {
        'reports': reports,
        'stats': stats,
        'status_choices': SafetyPost.STATUS_CHOICES,
        'category_choices': SafetyPost.CATEGORY_CHOICES,
        'severity_choices': SafetyPost.SEVERITY_CHOICES,
        'current_status': status_filter or 'all',
        'current_severity': severity_filter or 'all',
        'current_category': category_filter or 'all',
        'current_role': role_filter or 'all',
        'search_query': search_query,
        'map_markers_json': json.dumps(map_markers),
        'area_boundaries_json': json.dumps(area_boundaries),
    })