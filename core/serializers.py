from rest_framework import serializers
from .models import User, Incident, SafetyPost

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'role', 'phone_number', 'is_volunteer_opted_in', 'fcm_token')

class IncidentSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = Incident
        fields = ('id', 'user', 'latitude', 'longitude', 'status', 'created_at', 'acknowledged_by', 'acknowledged_at')
        read_only_fields = ('status', 'acknowledged_by', 'acknowledged_at')

class SafetyPostSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)

    class Meta:
        model = SafetyPost
        fields = ('id', 'author', 'post_type', 'title', 'description', 'latitude', 'longitude', 'image', 'created_at')