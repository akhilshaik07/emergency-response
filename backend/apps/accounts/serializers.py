"""Serializers for Profile and Authentication matching mentor assignment criteria."""

from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.models import Group
from django.db.models import Q
from apps.accounts.models import Profile
from apps.societies.models import GatedSociety


class ProfileSerializer(serializers.ModelSerializer):
    """Serializer for representing a user profile."""
    group_name = serializers.CharField(source='role_name', read_only=True)
    group_id = serializers.IntegerField(read_only=True)
    gated_society_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Profile
        fields = [
            'id',
            'username',
            'email',
            'mobile',
            'first_name',
            'last_name',
            'group_id',
            'group_name',
            'gated_society_id',
            'emergency_contact1',
            'emergency_contact2',
            'emergency_contact3',
            'medical_condition',
            'is_active',
            'date_joined',
            'last_login',
        ]
        read_only_fields = [
            'id',
            'group_id',
            'group_name',
            'gated_society_id',
            'is_active',
            'date_joined',
            'last_login',
        ]

    def to_representation(self, instance):
        """Mask medical_condition from unauthorized viewers (including Admin).

        MENTOR SPEC: Medical data is hidden from everyone except the person themselves
        and family guardians.
        """
        data = super().to_representation(instance)
        request = self.context.get('request')
        
        # If no request context or user is viewing another's profile outside active SOS
        if request and request.user.is_authenticated:
            is_self = (request.user.id == instance.id)
            # Guardian viewing family member in same society
            is_family_guardian = (
                request.user.group_id == 5 and 
                request.user.gated_society_id == instance.gated_society_id and
                request.user.gated_society_id is not None
            )
            if not (is_self or is_family_guardian):
                data['medical_condition'] = None
        else:
            data['medical_condition'] = None

        return data


class RegisterSerializer(serializers.ModelSerializer):
    """Registration serializer with email/mobile uniqueness and role restrictions."""
    password = serializers.CharField(write_only=True, min_length=8)
    group_id = serializers.IntegerField(required=False, default=5)
    gated_society_id = serializers.IntegerField(required=False, allow_null=True)

    class Meta:
        model = Profile
        fields = [
            'id',
            'email',
            'mobile',
            'password',
            'first_name',
            'last_name',
            'username',
            'group_id',
            'gated_society_id',
            'emergency_contact1',
            'emergency_contact2',
            'emergency_contact3',
            'medical_condition',
        ]

    def validate_email(self, value):
        if Profile.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email address already exists.")
        return value.lower()

    def validate_mobile(self, value):
        if Profile.objects.filter(mobile=value).exists():
            raise serializers.ValidationError("An account with this mobile number already exists.")
        return value

    def validate_group_id(self, value):
        # MENTOR SPEC: Admin (2) and Super Admin (1) cannot self-register
        if value in [1, 2]:
            raise serializers.ValidationError("Registration as Admin or Super Admin is not permitted via public registration.")
        if not Group.objects.filter(id=value).exists():
            raise serializers.ValidationError(f"Group with ID {value} does not exist.")
        return value

    def validate_gated_society_id(self, value):
        if value is not None and not GatedSociety.objects.filter(id=value).exists():
            raise serializers.ValidationError(f"Gated Society with ID {value} does not exist.")
        return value

    def create(self, validated_data):
        group_id = validated_data.pop('group_id', 5)
        gated_society_id = validated_data.pop('gated_society_id', None)
        password = validated_data.pop('password')

        group = Group.objects.filter(id=group_id).first()
        gated_society = GatedSociety.objects.filter(id=gated_society_id).first() if gated_society_id else None

        user = Profile(
            group=group,
            gated_society=gated_society,
            **validated_data
        )
        user.set_password(password)
        user.save()
        return user


class EmailOrMobileLoginSerializer(serializers.Serializer):
    """Login serializer strictly accepting Email OR Mobile + Password (NEVER username)."""
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    mobile = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get('email')
        mobile = attrs.get('mobile')
        password = attrs.get('password')

        if not email and not mobile:
            raise serializers.ValidationError("Either 'email' or 'mobile' must be provided for login.")

        # Lookup user by email OR mobile
        user = None
        if email:
            user = Profile.objects.filter(email__iexact=email).first()
        elif mobile:
            user = Profile.objects.filter(mobile=mobile).first()

        # Unified error message to prevent account enumeration
        if user is None or not user.check_password(password):
            raise serializers.ValidationError("Invalid email/mobile or password.")

        if not user.is_active:
            raise serializers.ValidationError("Invalid email/mobile or password.")

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        access = refresh.access_token

        return {
            'access': str(access),
            'refresh': str(refresh),
            'user': ProfileSerializer(user).data
        }


class ProfileUpdateSerializer(serializers.ModelSerializer):
    """Update serializer strictly limited to user-editable fields.

    LOCKED FIELDS: gated_society_id, group_id.
    NEVER EDITABLE: date_joined, is_staff, is_active, is_superuser.
    """
    class Meta:
        model = Profile
        fields = [
            'email',
            'first_name',
            'last_name',
            'username',
            'mobile',
            'emergency_contact1',
            'emergency_contact2',
            'emergency_contact3',
            'medical_condition',
        ]

    def validate_email(self, value):
        user = self.instance
        if Profile.objects.filter(email__iexact=value).exclude(id=user.id).exists():
            raise serializers.ValidationError("An account with this email address already exists.")
        return value.lower()

    def validate_mobile(self, value):
        user = self.instance
        if Profile.objects.filter(mobile=value).exclude(id=user.id).exists():
            raise serializers.ValidationError("An account with this mobile number already exists.")
        return value
