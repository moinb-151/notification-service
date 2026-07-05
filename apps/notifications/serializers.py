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
    user = UserRegistrationSerializer()

    class Meta:
        model = NotificationPreference
        fields = "__all__"
        read_only_fields = ["id", "quiet_start", "quiet_end"]
