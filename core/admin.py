from django.contrib import admin

# Register your models here.
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Incident, SafetyPost

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Township Info', {'fields': ('role', 'phone_number', 'is_volunteer_opted_in', 'fcm_token')}),
    )
    list_display = ('username', 'email', 'role', 'is_volunteer_opted_in', 'is_staff')
    list_filter = ('role', 'is_volunteer_opted_in', 'is_staff')

@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'status', 'created_at', 'acknowledged_by', 'acknowledged_at')
    list_filter = ('status', 'created_at')
    search_fields = ('user__username', 'acknowledged_by__username')

@admin.register(SafetyPost)
class SafetyPostAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'post_type', 'author', 'created_at')
    list_filter = ('post_type', 'created_at')
    search_fields = ('title', 'description', 'author__username')