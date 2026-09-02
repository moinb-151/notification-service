import logging

from ..models import Notification
from ..services.notification_service import NotificationService


logger = logging.getLogger(__name__)


class NotificationDLQService:

    @staticmethod
    def extract_notification_id(message):
        try:
            return message[1]["notification_id"]["__value__"]["hex"]
        except (IndexError, KeyError, TypeError):
            return None

    @staticmethod
    def handle(notification_id, task_id, retries, headers):
        notification = NotificationService.get_notification_by_id(
            notification_id
        )

        if notification is None:
            logger.error(
                "DLQ notification not found",
                extra={
                    "notification_id": str(notification_id),
                    "task_id": task_id,
                },
            )
            return

        death = headers.get("x-death", [{}])[0]

        logger.error(
            "Notification moved to DLQ",
            extra={
                "notification_id": str(notification.id),
                "task_id": task_id,
                "status": notification.status,
                "error_message": notification.error_message,
                "attempts": notification.attempts,
                "retries": retries,
                "task": headers.get("task"),
                "death_reason": death.get("reason"),
                "death_queue": death.get("queue"),
                "death_count": death.get("count"),
            },
        )