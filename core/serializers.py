from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from .models import Area, Device, Property, User, Incident, SafetyPost, CommunityPost, CommunityPostComment, CommunityPostLike


class AreaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Area
        fields = ('id', 'name', 'center_latitude', 'center_longitude', 'radius_m')


class PropertySerializer(serializers.ModelSerializer):
    resident_count = serializers.IntegerField(source='residents.count', read_only=True)

    class Meta:
        model = Property
        fields = ('id', 'area', 'unit_number', 'address_line', 'postal_code', 'property_type',
                  'latitude', 'longitude', 'is_active', 'created_at', 'resident_count')
        read_only_fields = ('id', 'created_at', 'resident_count')

class UserSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        registered_property = attrs.get('residence')
        if registered_property:
            attrs['area'] = registered_property.area
        return attrs

    class Meta:
        model = User
        fields = ('id', 'username', 'role', 'phone_number', 'unit_address', 'area', 'residence',
                  'is_volunteer_opted_in', 'is_verified_volunteer')
        read_only_fields = ('role', 'is_verified_volunteer')


class MobileProfileSerializer(serializers.ModelSerializer):
    """The fields a resident may view or update for their own account."""

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'role', 'phone_number',
                  'unit_address', 'area', 'residence', 'is_volunteer_opted_in',
                  'is_verified_volunteer')
        read_only_fields = ('id', 'username', 'role', 'area', 'residence', 'is_verified_volunteer')


class RegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    residence = serializers.PrimaryKeyRelatedField(
        queryset=Property.objects.filter(is_active=True), required=False, allow_null=True
    )
    unit_address = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')

    class Meta:
        model = User
        fields = ('username', 'password', 'email', 'first_name', 'last_name', 'phone_number',
                  'unit_address', 'residence')

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        registered_property = validated_data.pop('residence', None)
        user = User(**validated_data, role='resident', residence=registered_property)
        if registered_property:
            user.area = registered_property.area
        user.set_password(validated_data['password'])
        user.save()
        return user


class LocationUpdateSerializer(serializers.Serializer):
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, min_value=-90, max_value=90)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, min_value=-180, max_value=180)


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
        extra_kwargs = {
            'message': {'required': False, 'allow_blank': True, 'default': ''},
            'incident_type': {'required': False, 'default': 'other'},
        }

    def validate_incident_type(self, value):
        valid_choices = [c[0] for c in Incident.TYPE_CHOICES]
        if value in valid_choices:
            return value
        if value and value.lower() == 'sos':
            return 'other'
        return 'other'

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

class CommunityPostSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source='author.username', read_only=True)
    author_area = serializers.CharField(source='author.area.name', read_only=True, default="Unknown Area")
    likes_count = serializers.IntegerField(source='likes.count', read_only=True)
    comments_count = serializers.IntegerField(source='comment_count', read_only=True)
    is_liked = serializers.SerializerMethodField()

    class Meta:
        model = CommunityPost
        fields = ['id', 'author_name', 'author_area', 'title', 'content', 'is_hidden', 'created_at', 'likes_count', 'comments_count', 'is_liked']
        read_only_fields = ['is_hidden', 'created_at', 'likes_count', 'comments_count', 'is_liked']

    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            return obj.is_liked_by(request.user)
        return False

    def create(self, validated_data):
        # Automatically tie the post to the user making the API request
        validated_data['author'] = self.context['request'].user
        return super().create(validated_data)


class CommunityPostCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source='author.username', read_only=True)
    author_role = serializers.CharField(source='author.role', read_only=True)

    class Meta:
        model = CommunityPostComment
        fields = ['id', 'post', 'author_name', 'author_role', 'content', 'is_hidden', 'created_at']
        read_only_fields = ['is_hidden', 'created_at']

    def create(self, validated_data):
        validated_data['author'] = self.context['request'].user
        return super().create(validated_data)

