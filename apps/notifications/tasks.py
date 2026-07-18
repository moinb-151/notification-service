from celery import shared_task
from .services import NotificationTemplateService, NotificationService
from .providers.email import EmailProvider


@shared_task
def process_notification(notification_id):
    notification = NotificationService.get_notification_by_id(notification_id)

    notification_template = NotificationTemplateService.get_template(
        event_type=notification.event_type,
        channel=notification.channel
    )

    subject, body = NotificationTemplateService.render_template(
        template=notification_template,
        context={}
    )
    
# @shared_task
# def send_email_notification(notification_id, user):
#     notification = NotificationService.get_notification(
#         notification_id=notification_id,
#         user=user
#     )

    