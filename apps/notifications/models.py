import uuid_utils.compat as uuid
from django.contrib.auth import get_user_model
from django.db import models

from ..orders.models import Order
from common.choices import ChannelType

User = get_user_model()


def generate_uuid7():
    return uuid.uuid7()


class NotificationStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    SENT = "sent", "Sent"
    FAILED = "failed", "Failed"
    SUPPRESSED = "suppressed", "Suppressed"


class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=generate_uuid7, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notifications"
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        related_name="notifications",
        null=True,
        blank=True,
    )
    channel = models.CharField(max_length=20, choices=ChannelType.choices)
    event_type = models.CharField(max_length=64)
    status = models.CharField(
        max_length=20,
        choices=NotificationStatus.choices,
        default=NotificationStatus.PENDING,
    )
    idempotency_key = models.CharField(max_length=128, unique=True)
    payload = models.JSONField(default=dict, blank=True)
    provider_message_id = models.CharField(max_length=255, null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_attempted_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "-created_at"], name="user_created_at_idx"),
            models.Index(
                fields=["status", "last_attempted_at"], name="status_attempt_idx"
            ),
            models.Index(fields=["status"], name="notification_status_idx"),
            models.Index(fields=["order"], name="notification_order_idx"),
            models.Index(fields=["event_type"], name="event_type_idx"),
        ]

    def __str__(self):
        return f"{self.event_type} ({self.channel})"


class NotificationTemplate(models.Model):
    id = models.UUIDField(primary_key=True, default=generate_uuid7, editable=False)
    event_type = models.CharField(max_length=64)
    channel = models.CharField(max_length=20, choices=ChannelType.choices)
    subject = models.CharField(max_length=255, blank=True)
    body_template = models.TextField()
    version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "event_type",
                    "channel",
                    "version",
                ],
                name="unique_template_version",
            )
        ]
