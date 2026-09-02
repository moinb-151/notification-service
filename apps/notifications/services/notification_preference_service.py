from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from ...users.models import NotificationPreference


class NotificationPreferenceService:
    @staticmethod
    def get_preferences(user):
        preferences = NotificationPreference.objects.filter(user=user).select_related(
            "user"
        )
        return preferences

    @staticmethod
    def get_preference_by_channel(user, channel):
        preference = NotificationPreference.objects.filter(
            user=user,
            channel=channel,
        ).first()

        return preference

    @staticmethod
    def is_in_quiet_hours(preference):
        if (
            preference is None
            or preference.quiet_start is None
            or preference.quiet_end is None
        ):
            return False

        user_timezone = ZoneInfo(preference.timezone)
        current_time = timezone.now().astimezone(user_timezone).time()

        quiet_start = preference.quiet_start
        quiet_end = preference.quiet_end

        # Example: 22:00 -> 07:00
        if quiet_start > quiet_end:
            return current_time >= quiet_start or current_time < quiet_end

        # Example: 13:00 -> 17:00
        return quiet_start <= current_time < quiet_end

    @staticmethod
    def get_next_allowed_time(preference):
        if preference.quiet_start is None or preference.quiet_end is None:
            return None

        user_timezone = ZoneInfo(preference.timezone)
        now = timezone.now().astimezone(user_timezone)

        quiet_start = datetime.combine(
            now.date(), preference.quiet_start, tzinfo=user_timezone
        )
        quiet_end = datetime.combine(
            now.date(), preference.quiet_end, tzinfo=user_timezone
        )

        # Quiet hours cross midnight (e.g. 22:00 -> 07:00)
        if quiet_start >= quiet_end:
            quiet_end += timedelta(days=1)

            # If it's after midnight but before quiet_end,
            # quiet_start belongs to yesterday.
            if now.time() < preference.quiet_end:
                quiet_start -= timedelta(days=1)
                quiet_end -= timedelta(days=1)

        return quiet_end

    @staticmethod
    @transaction.atomic
    def update_preference(user, channel, validated_data):
        try:
            preference = NotificationPreference.objects.select_for_update().get(
                channel=channel,
                user=user,
            )

            for field, value in validated_data.items():
                setattr(preference, field, value)

            preference.save(update_fields=validated_data.keys())

            return preference
        except NotificationPreference.DoesNotExist:
            return None

    @staticmethod
    @transaction.atomic
    def replace_preferences(user, preferences_data):
        preferences = NotificationPreference.objects.select_for_update().filter(
            user=user
        )

        preference_map = {preference.channel: preference for preference in preferences}

        modified_preferences = []

        for data in preferences_data:
            preference = preference_map.get(data["channel"])

            if preference is None:
                raise ValidationError(
                    {"channel": f"Invalid channel: {data['channel']}"}
                )

            for field in ("enabled", "quiet_start", "quiet_end"):
                if field in data:
                    setattr(preference, field, data[field])

            modified_preferences.append(preference)

        if modified_preferences:
            NotificationPreference.objects.bulk_update(
                modified_preferences,
                ["enabled", "quiet_start", "quiet_end"],
            )

        return modified_preferences
