from dataclasses import dataclass
from datetime import time
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from ..users.models import NotificationPreference
from .models import Notification, NotificationStatus


@dataclass(frozen=True)
class CreateNotificationResult:
    notification: Notification
    created: bool


class NotificationService:
    @staticmethod
    def create_notification(validated_data):
        notification, created = Notification.objects.get_or_create(
            idempotency_key=validated_data["idempotency_key"],
            defaults=validated_data,
        )

        return CreateNotificationResult(notification, created)

    @staticmethod
    def list_notifications(user, **filters):
        queryset = (
            Notification.objects.filter(user=user)
            .select_related("user", "order")
            .order_by("-created_at")
        )

        channel = filters.get("channel")
        if channel is not None:
            queryset = queryset.filter(channel=channel)

        is_read = filters.get("is_read")
        if is_read is not None:
            queryset = queryset.filter(is_read=is_read)

        status = filters.get("status")
        if status is not None:
            queryset = queryset.filter(status=status)

        event_type = filters.get("event_type")
        if event_type is not None:
            queryset = queryset.filter(event_type=event_type)

        return queryset

    @staticmethod
    def get_notification(notification_id, user):
        return (
            Notification.objects.filter(
                id=notification_id,
                user=user,
            )
            .select_related("user")
            .first()
        )

    @staticmethod
    def _is_channel_enabled(user, channel):
        preference = (
            NotificationPreference.objects.filter(
                user=user,
                channel=channel,
            )
            .only("enabled")
            .first()
        )

        if preference is None:
            return True

        return preference.enabled

    @staticmethod
    def _is_in_quiet_hours(user, channel):
        preference = (
            NotificationPreference.objects.filter(
                user=user,
                channel=channel,
            )
            .only(
                "quiet_start",
                "quiet_end",
            )
            .first()
        )

        if (
            preference is None
            or preference.quiet_start is None
            or preference.quiet_end is None
        ):
            return False

        user_timezone = ZoneInfo(user.timezone)
        current_time = timezone.now().astimezone(user_timezone).time()

        quiet_start = preference.quiet_start
        quiet_end = preference.quiet_end

        # Example: 22:00 -> 07:00
        if quiet_start > quiet_end:
            return current_time >= quiet_start or current_time < quiet_end

        # Example: 13:00 -> 17:00
        return quiet_start <= current_time < quiet_end

    @staticmethod
    @transaction.atomic
    def mark_as_read(notification_id, user):
        try:
            notification = Notification.objects.select_for_update().get(
                id=notification_id, user=user
            )
            if notification.is_read:
                return notification
            notification.is_read = True
            notification.save(update_fields=["is_read"])
            return notification
        except Notification.DoesNotExist:
            return None

    @staticmethod
    @transaction.atomic
    def record_delivery(notification_id, provider_message_id):
        try:
            notification = Notification.objects.select_for_update().get(
                id=notification_id
            )

            notification.status = NotificationStatus.SENT
            notification.provider_message_id = provider_message_id
            notification.attempts += 1
            notification.last_attempted_at = timezone.now()
            notification.sent_at = timezone.now()

            notification.save(
                update_fields=[
                    "status",
                    "provider_message_id",
                    "attempts",
                    "last_attempted_at",
                    "sent_at",
                ]
            )

            return notification

        except Notification.DoesNotExist:
            return None

    @staticmethod
    @transaction.atomic
    def record_failure(notification_id, error_message):
        try:
            notification = Notification.objects.select_for_update().get(
                id=notification_id
            )

            notification.status = NotificationStatus.FAILED
            notification.attempts += 1
            notification.last_attempted_at = timezone.now()

            notification.save(
                update_fields=[
                    "status",
                    "attempts",
                    "last_attempted_at",
                ]
            )

            return notification

        except Notification.DoesNotExist:
            return None
