from django.template import Context, Template

from ..models import NotificationTemplate


class NotificationTemplateService:
    @staticmethod
    def get_template(event_type: str, channel: str) -> NotificationTemplate | None:
        try:
            return NotificationTemplate.objects.get(
                event_type=event_type,
                channel=channel,
            )
        except NotificationTemplate.DoesNotExist:
            return None

    @staticmethod
    def render(template: str, context: dict) -> str:
        return Template(template).render(Context(context))

    @staticmethod
    def render_template(
        template: NotificationTemplate, context: dict
    ) -> tuple[str, str, str | None]:
        subject = NotificationTemplateService.render(template.subject, context)
        
        body = NotificationTemplateService.render(template.body_template, context)

        html_body = None
        if template.html_body_template:
            html_body = NotificationTemplateService.render(
                template.html_body_template,
                context,
            )

        return subject, body, html_body
