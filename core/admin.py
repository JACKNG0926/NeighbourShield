from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils import timezone

# Removed 'Street' from the imports
from .models import (User, Area, Property, Device, EscalationPolicy, Incident, Notification,
                     Acknowledgement, IncidentLog, SafetyPost, BroadcastRecipient)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
class ReadOnlyAdmin(admin.ModelAdmin):
    """Audit-style tables: view only, nobody can add, edit or delete from the admin."""
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ReadOnlyInline(admin.TabularInline):
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.action(description='Approve selected users as volunteers')
def approve_volunteers(modeladmin, request, queryset):
    for user in queryset:
        user.set_volunteer_verified(True, request.user)
        user.save(update_fields=[
            'role', 'is_volunteer_opted_in', 'is_verified_volunteer',
            'volunteer_verified_by', 'volunteer_verified_at',
        ])

def _is_township_admin(user):
    return user.is_superuser or getattr(user, 'role', '') == 'admin'


# ---------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------
@admin.register(User)
class CustomUserAdmin(UserAdmin):
    # Precise location (last_latitude / last_longitude) and FCM tokens are deliberately
    # NOT shown anywhere in the admin.
    fieldsets = UserAdmin.fieldsets + (
        ('Township Info', {'fields': (
            'role', 'phone_number', 'unit_address', 'area', 'residence',
            'is_volunteer_opted_in', 'is_verified_volunteer',
            'volunteer_verified_by', 'volunteer_verified_at', 'last_location_at')}),
    )
    # Without this, users created in the admin get no township fields.
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Township Info', {'fields': ('role', 'phone_number', 'unit_address', 'area', 'residence')}),
    )
    list_display = ('username', 'email', 'role', 'area', 'residence', 'is_volunteer_opted_in',
                    'is_verified_volunteer', 'is_active', 'is_staff')
    list_filter = ('role', 'area', 'is_volunteer_opted_in', 'is_verified_volunteer',
                   'is_active', 'is_staff')
    list_select_related = ('area', 'residence')

    actions = [approve_volunteers]

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        readonly += ['volunteer_verified_by', 'volunteer_verified_at', 'last_location_at']
        if not request.user.is_superuser:
            # Only superusers may change roles or verify volunteers.
            readonly += ['role', 'is_verified_volunteer']
        return readonly

    def save_model(self, request, obj, form, change):
        if obj.residence_id:
            # A resident's area always follows their registered property.
            obj.area = obj.residence.area
            
        if 'is_verified_volunteer' in form.changed_data:
            # Use the new single source of truth method
            obj.set_volunteer_verified(obj.is_verified_volunteer, request.user)
            
        super().save_model(request, obj, form, change)


@admin.register(Device)
class DeviceAdmin(ReadOnlyAdmin):
    list_display = ('user', 'platform', 'is_active', 'last_seen')
    list_filter = ('platform', 'is_active')
    search_fields = ('user__username',)
    exclude = ('fcm_token',)           # tokens are credentials, keep them out of the UI
    list_select_related = ('user',)


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ('name', 'center_latitude', 'center_longitude', 'radius_m')
    search_fields = ('name',)


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ('unit_number', 'address_line', 'area', 'property_type', 'is_active')
    list_filter = ('area', 'property_type', 'is_active')
    search_fields = ('unit_number', 'address_line', 'postal_code')
    list_select_related = ('area',)


# ---------------------------------------------------------------------
# SOS workflow
# ---------------------------------------------------------------------
@admin.register(EscalationPolicy)
class EscalationPolicyAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'ack_timeout_seconds', 'volunteer_radius_m', 'max_level')

    def has_add_permission(self, request):
        return not EscalationPolicy.objects.exists()     # single-row table

    def has_delete_permission(self, request, obj=None):
        return False


class AcknowledgementInline(ReadOnlyInline):
    model = Acknowledgement
    fields = ('responder', 'responder_type', 'acknowledged_at', 'eta_minutes', 'note')


class IncidentLogInline(ReadOnlyInline):
    model = IncidentLog
    fields = ('timestamp', 'action', 'actor', 'detail', 'data')


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'incident_type', 'status', 'escalation_level',
                    'created_at', 'acknowledged_by', 'acknowledged_at', 'resolved_at')
    list_filter = ('status', 'incident_type', 'created_at')
    search_fields = ('user__username', 'acknowledged_by__username')
    list_select_related = ('user', 'acknowledged_by')
    date_hierarchy = 'created_at'
    inlines = [AcknowledgementInline, IncidentLogInline]

    # Admins may only change the status and resolution note.
    readonly_fields = ('user', 'latitude', 'longitude', 'message', 'incident_type',
                       'created_at', 'escalation_level', 'next_escalation_at', 'escalated_at',
                       'acknowledged_by', 'acknowledged_at', 'resolved_at', 'resolved_by')

    def has_add_permission(self, request):
        return False                    # SOS incidents come from the API only

    def has_delete_permission(self, request, obj=None):
        return False                    # keep history for analytics

    def save_model(self, request, obj, form, change):
        status_changed = change and 'status' in form.changed_data
        if status_changed:
            if obj.status == 'resolved':
                obj.resolved_at = timezone.now()
                obj.resolved_by = request.user
            if obj.status in ('resolved', 'cancelled'):
                obj.next_escalation_at = None
        super().save_model(request, obj, form, change)
        if status_changed:
            action = obj.status if obj.status in ('resolved', 'cancelled') else 'status_changed'
            IncidentLog.objects.create(
                incident=obj, action=action, actor=request.user,
                detail=f'Status set to {obj.status} via admin')


@admin.register(Notification)
class NotificationAdmin(ReadOnlyAdmin):
    list_display = ('id', 'incident', 'recipient', 'audience', 'escalation_level',
                    'status', 'attempts', 'created_at')
    list_filter = ('status', 'audience', 'escalation_level')
    list_select_related = ('incident', 'recipient')


@admin.register(Acknowledgement)
class AcknowledgementAdmin(ReadOnlyAdmin):
    list_display = ('id', 'incident', 'responder', 'responder_type', 'eta_minutes',
                    'acknowledged_at')
    list_filter = ('responder_type',)
    list_select_related = ('incident', 'responder')


@admin.register(IncidentLog)
class IncidentLogAdmin(ReadOnlyAdmin):
    list_display = ('id', 'incident', 'action', 'actor', 'timestamp')
    list_filter = ('action',)
    list_select_related = ('incident', 'actor')


# ---------------------------------------------------------------------
# Safety feed + broadcast
# ---------------------------------------------------------------------
@admin.register(SafetyPost)
class SafetyPostAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'post_type', 'category', 'author', 'area',
                    'is_verified', 'status', 'created_at')
    list_filter = ('post_type', 'category', 'is_verified', 'status', 'area', 'created_at')
    search_fields = ('title', 'description', 'author__username')
    list_select_related = ('author', 'area')
    filter_horizontal = ('affected_areas',)
    date_hierarchy = 'created_at'

    def get_readonly_fields(self, request, obj=None):
        readonly = ['verified_by', 'verified_at', 'resolved_at']
        if not _is_township_admin(request.user):
            readonly.append('is_verified')
        return readonly

    def save_model(self, request, obj, form, change):
        if 'is_verified' in form.changed_data:
            if obj.is_verified:
                obj.verified_by = request.user
                obj.verified_at = timezone.now()
            else:
                obj.verified_by = None
                obj.verified_at = None
        if 'status' in form.changed_data:
            obj.resolved_at = timezone.now() if obj.status == 'resolved' else None
        super().save_model(request, obj, form, change)


@admin.register(BroadcastRecipient)
class BroadcastRecipientAdmin(ReadOnlyAdmin):
    list_display = ('post', 'user', 'delivered', 'delivered_at', 'read_at')
    list_filter = ('delivered',)
    list_select_related = ('post', 'user')