from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from ..models import Notification, NotificationStatus


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
    def get_notification_by_id(notification_id):
        try:
            return Notification.objects.select_related("user", "order").get(
                id=notification_id,
            )
        except Notification.DoesNotExist:
            return None

    @staticmethod
    @transaction.atomic
    def update_notification(user, notification_id, validated_data):
        try:
            notification = Notification.objects.select_for_update().get(
                id=notification_id,
                user=user,
            )

            for field, value in validated_data.items():
                setattr(notification, field, value)

            notification.save(update_fields=validated_data.keys())
            return notification
        except Notification.DoesNotExist:
            return None

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
            notification.read_at = timezone.now()
            notification.save(update_fields=["is_read", "read_at"])
            return notification
        except Notification.DoesNotExist:
            return None

    @staticmethod
    @transaction.atomic
    def record_attempt(notification_id):
        try:
            notification = Notification.objects.select_for_update().get(
                id=notification_id
            )

            notification.attempts += 1
            notification.last_attempted_at = timezone.now()

            notification.save(
                update_fields=[
                    "attempts",
                    "last_attempted_at",
                ]
            )

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
            notification.error_message = None
            notification.sent_at = timezone.now()

            notification.save(
                update_fields=[
                    "status",
                    "provider_message_id",
                    "error_message",
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
            notification.error_message = error_message

            notification.save(
                update_fields=[
                    "status",
                    "error_message",
                ]
            )

            return notification

        except Notification.DoesNotExist:
            return None

    @staticmethod
    @transaction.atomic
    def defer_notification(
        notification_id,
        user,
        scheduled_for,
    ):
        try:
            notification = Notification.objects.select_for_update().get(
                id=notification_id,
                user=user,
            )

            notification.status = NotificationStatus.DEFERRED
            notification.scheduled_for = scheduled_for

            notification.save(
                update_fields=[
                    "status",
                    "scheduled_for",
                ]
            )

            return notification

        except Notification.DoesNotExist:
            return None

    @staticmethod
    @transaction.atomic
    def mark_suppressed(notification_id, user):
        return NotificationService.update_notification(
            notification_id=notification_id,
            user=user,
            validated_data={
                "status": NotificationStatus.SUPPRESSED,
            },
        )
