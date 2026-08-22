from rest_framework import serializers

from ..orders.serializers import OrderSerializer
from ..users.models import NotificationPreference
from ..users.serializers import UserRegistrationSerializer
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    user = UserRegistrationSerializer()
    order = OrderSerializer()

    class Meta:
        model = Notification
        fields = [
            "id",
            "user",
            "order",
            "channel",
            "event_type",
            "status",
            "payload",
            "provider_message_id",
            "is_read",
            "attempts",
            "last_attempted_at",
            "sent_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "provider_message_id",
            "attempts",
            "last_attempted_at",
            "sent_at",
            "created_at",
            "updated_at",
        ]


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    user = UserRegistrationSerializer(read_only=True)

    class Meta:
        model = NotificationPreference
        fields = [
            "id",
            "user",
            "channel",
            "enabled",
            "quiet_start",
            "quiet_end",
        ]
        read_only_fields = fields


class NotificationPreferenceUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = [
            "enabled",
            "timezone",
            "quiet_start",
            "quiet_end",
        ]


class NotificationPreferenceUpdateItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = [
            "channel",
            "enabled",
            "quiet_start",
            "quiet_end",
        ]


class NotificationPreferenceBulkUpdateSerializer(serializers.Serializer):
    preferences = NotificationPreferenceUpdateItemSerializer(many=True)
