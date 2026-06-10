import zoneinfo

import uuid_utils.compat as uuid
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models


def generate_uuid7():
    return uuid.uuid7()


def get_timezone_choices():
    timezones = sorted(zoneinfo.available_timezones())
    return [(tz, tz) for tz in timezones]


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=generate_uuid7, editable=False)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["updated_at"]),
        ]


class NotificationPreference(models.Model):
    class CHANNEL_TYPES(models.TextChoices):
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"
        PUSH = "push", "Push Notification"

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notification_preference"
    )
    channel = models.CharField(max_length=20, choices=CHANNEL_TYPES.choices)
    enabled = models.BooleanField(default=True)
    timezone = models.CharField(
        max_length=50, choices=get_timezone_choices(), default="UTC"
    )
    quiet_start = models.TimeField(null=True, blank=True)
    quiet_end = models.TimeField(null=True, blank=True)

    def clean(self):
        super().clean()
        if self.quiet_start and not self.quiet_end:
            raise ValidationError(
                {
                    "quiet_end": "You must specify an end time if a start time is provided."
                }
            )

        if self.quiet_end and not self.quiet_start:
            raise ValidationError(
                {
                    "quiet_start": "You must specify a start time if an end time is provided."
                }
            )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "channel"], name="unique_user_channel_preference"
            )
        ]

        indexes = [
            models.Index(
                fields=["channel"],
                condition=models.Q(enabled=True),
                name="idx_preference_channel_enabled",
            )
        ]
