"""Serializers for GatedSociety matching mentor assignment schema."""

from rest_framework import serializers
from apps.societies.models import GatedSociety
from apps.accounts.models import Profile


class GatedSocietySerializer(serializers.ModelSerializer):
    """Gated Society serializer."""
    sub_admin_email = serializers.EmailField(source='sub_admin.email', read_only=True)
    sub_admin_id = serializers.IntegerField(required=False, allow_null=True)

    class Meta:
        model = GatedSociety
        fields = [
            'id',
            'name',
            'owner',
            'in_charge',
            'sub_admin_id',
            'sub_admin_email',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_sub_admin_id(self, value):
        if value is not None and not Profile.objects.filter(id=value).exists():
            raise serializers.ValidationError(f"User with ID {value} does not exist.")
        return value

    def create(self, validated_data):
        sub_admin_id = validated_data.pop('sub_admin_id', None)
        sub_admin = Profile.objects.filter(id=sub_admin_id).first() if sub_admin_id else None
        society = GatedSociety.objects.create(sub_admin=sub_admin, **validated_data)
        return society

    def update(self, instance, validated_data):
        if 'sub_admin_id' in validated_data:
            sub_admin_id = validated_data.pop('sub_admin_id')
            instance.sub_admin = Profile.objects.filter(id=sub_admin_id).first() if sub_admin_id else None
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance
