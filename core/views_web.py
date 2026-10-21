import json
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Count
from .forms import AreaRegistrationForm, PropertyRegistrationForm
from .models import Area, Incident, Property, SafetyPost, CommunityPost
from .forms import AreaRegistrationForm, PropertyRegistrationForm, BroadcastForm
from django.utils import timezone
from .models import Area, Incident, Property, SafetyPost, User


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