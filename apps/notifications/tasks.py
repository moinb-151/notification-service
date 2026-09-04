from celery import shared_task
from django.conf import settings
from django.utils import timezone
from django.db import transaction

from common.choices import ChannelType

from .models import Notification, NotificationStatus, NotificationEventType
from .providers.email import EmailProvider
from .providers.sms import SMSProvider
from .services.notification_preference_service import NotificationPreferenceService
from .services.notification_service import NotificationService
from .services.notification_template_service import NotificationTemplateService
from .exceptions import (
    NotificationProviderError,
    TransientNotificationProviderError,
    PermanentNotificationProviderError,
)


@shared_task(bind=True)
def process_notification(self, notification_id):
    notification = NotificationService.get_notification_by_id(notification_id)

    if notification is None:
        return

    preference = NotificationPreferenceService.get_preference_by_channel(
        user=notification.user,
        channel=notification.channel,
    )

    # Preference not found
    if preference is None:
        NotificationService.record_failure(
            notification_id=notification.id,
            error_message="Notification preference not found.",
        )
        return

    # Channel disabled
    if not preference.enabled:
        NotificationService.mark_suppressed(
            notification_id=notification.id,
            user=notification.user,
        )
        return

    # Quiet hours
    if NotificationPreferenceService.is_in_quiet_hours(preference):
        next_allowed_time = NotificationPreferenceService.get_next_allowed_time(
            preference
        )

        NotificationService.defer_notification(
            notification_id=notification.id,
            user=notification.user,
            scheduled_for=next_allowed_time,
        )

        return

    # Template
    notification_template = NotificationTemplateService.get_template(
        event_type=notification.event_type,
        channel=notification.channel,
    )

    if notification_template is None:
        NotificationService.record_failure(
            notification_id=notification.id,
            error_message=(
                f"No template found for "
                f"{notification.event_type}/{notification.channel}."
            ),
        )
        return

    # Render
    subject, body = NotificationTemplateService.render_template(
        template=notification_template,
        context=notification.payload,
    )

    NotificationService.record_attempt(
        notification_id=notification.id,
    )

    try:
        match notification.channel:
            case ChannelType.EMAIL:
                message_id = EmailProvider.send(
                    to=notification.user.email,
                    subject=subject,
                    body=body,
                )
            case ChannelType.SMS:
                message_id = SMSProvider.send(
                    phone_number=notification.user.phone,
                    message=body,
                )
            case _:
                NotificationService.record_failure(
                    notification_id=notification.id,
                    error_message=f"Unsupported channel: {notification.channel}.",
                )
                return
    except TransientNotificationProviderError as exc:
        if self.request.retries >= settings.NOTIFICATION_MAX_RETRIES:
            NotificationService.record_failure(
                notification_id=notification.id,
                error_message="Max retries reached.",
            )
            raise exc

        raise self.retry(
            exc=exc,
            countdown=settings.NOTIFICATION_RETRY_BACKOFF * (2**self.request.retries),
        )

    except PermanentNotificationProviderError as exc:
        NotificationService.record_failure(
            notification_id=notification.id,
            error_message=str(exc),
        )
        return

    except NotificationProviderError as exc:
        NotificationService.record_failure(
            notification_id=notification.id,
            error_message=str(exc),
        )
        return

    NotificationService.record_delivery(
        notification_id=notification.id,
        provider_message_id=message_id,
    )


@shared_task
def process_deferred_notifications():
    now = timezone.now()

    with transaction.atomic():
        notifications = list(
            Notification.objects.select_for_update(skip_locked=True).filter(
                status=NotificationStatus.DEFERRED,
                scheduled_for__lte=now,
            )
        )

        for notification in notifications:
            notification.status = NotificationStatus.PENDING
            notification.scheduled_for = None

            notification.save(
                update_fields=[
                    "status",
                    "scheduled_for",
                ]
            )

    for notification in notifications:
        process_notification.delay(
            notification_id=notification.id,
        )
