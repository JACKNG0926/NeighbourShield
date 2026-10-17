from rest_framework import serializers
from .models import Device, User, Incident, SafetyPost

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'role', 'phone_number', 'unit_address', 'area',
                  'is_volunteer_opted_in', 'is_verified_volunteer')
        read_only_fields = ('role', 'is_verified_volunteer')


class DeviceSerializer(serializers.ModelSerializer):
    """A device token may be submitted but is never returned in API responses."""

    fcm_token = serializers.CharField(write_only=True)

    class Meta:
        model = Device
        fields = ('id', 'fcm_token', 'platform', 'is_active', 'created_at', 'last_seen')
        read_only_fields = ('id', 'created_at', 'last_seen')

class IncidentSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    acknowledged_by = UserSerializer(read_only=True)

    class Meta:
        model = Incident
        fields = ('id', 'user', 'latitude', 'longitude', 'message', 'incident_type', 'status',
                  'created_at', 'escalation_level', 'next_escalation_at', 'acknowledged_by',
                  'acknowledged_at', 'resolved_at', 'resolution_note')
        read_only_fields = ('user', 'status', 'escalation_level', 'next_escalation_at',
                            'acknowledged_by', 'acknowledged_at', 'resolved_at', 'resolution_note')

class SafetyPostSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)

    class Meta:
        model = SafetyPost
        fields = ('id', 'author', 'post_type', 'category', 'title', 'description', 'latitude',
                  'longitude', 'image', 'area', 'affected_areas', 'severity', 'status',
                  'is_verified', 'verified_at', 'resolved_at', 'expires_at', 'created_at')
        read_only_fields = ('author', 'status', 'is_verified', 'verified_at', 'resolved_at',
                            'created_at')

    def validate_post_type(self, value):
        user = self.context['request'].user
        if value in ('announcement', 'broadcast') and not user.is_township_admin:
            raise serializers.ValidationError('Only township administrators may publish official posts.')
        if value == 'broadcast' and not user.has_perm('core.send_broadcast'):
            raise serializers.ValidationError('You do not have permission to send broadcasts.')
        return value

    def validate(self, attrs):
        user = self.context['request'].user
        if not user.is_township_admin:
            if attrs.get('post_type', getattr(self.instance, 'post_type', 'hazard')) != 'hazard':
                raise serializers.ValidationError('Residents may only create or edit hazard reports.')
            if 'affected_areas' in attrs:
                raise serializers.ValidationError({'affected_areas': 'Only administrators may target areas.'})
        return attrs
