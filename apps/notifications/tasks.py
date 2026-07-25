from celery import shared_task

from .models import NotificationStatus
from .providers.choices import PROVIDERS
from .services import (
    NotificationPreferenceService,
    NotificationService,
    NotificationTemplateService,
)


@shared_task
def process_notification(notification_id):
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
        NotificationService.update_notification(
            notification_id=notification.id,
            user=notification.user,
            validated_data={
                "status": NotificationStatus.SUPPRESSED,
            },
        )

        NotificationService.record_failure(
            notification_id=notification.id,
            error_message="Notification channel is disabled.",
        )
        return

    # Quiet hours
    if NotificationPreferenceService.is_in_quiet_hours(preference):
        next_allowed_time = NotificationPreferenceService.get_next_allowed_time(
            preference
        )

        NotificationService.update_notification(
            notification_id=notification.id,
            user=notification.user,
            validated_data={
                "status": NotificationStatus.DEFERRED,
                "scheduled_for": next_allowed_time,
            },
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

    provider = PROVIDERS[notification.channel]

    try:
        message_id = provider.send(  # ty: ignore[unresolved-attribute]
            to=notification.payload["email"],
            subject=subject,
            body=body,
        )

    except Exception as exc:
        NotificationService.record_failure(
            notification_id=notification.id,
            error_message=str(exc),
        )
        return

    NotificationService.record_delivery(
        notification_id=notification.id,
        provider_message_id=message_id,
    )


# @shared_task
# def send_email_notification(notification_id, user):
#     notification = NotificationService.get_notification(
#         notification_id=notification_id,
#         user=user
#     )
