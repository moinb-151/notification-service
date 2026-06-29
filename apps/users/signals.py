from django.db.models.signals import post_save
from django.dispatch import receiver

from common.choices import ChannelType

from .models import NotificationPreference, User


@receiver(post_save, sender=User)
def seed_notification_preference(sender, instance, created, **kwargs):
    if not created:
        return
    NotificationPreference.objects.bulk_create(
        [
            NotificationPreference(user=instance, channel=value)
            for value, _ in ChannelType.choices
        ]
    )
