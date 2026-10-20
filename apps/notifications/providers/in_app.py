import json
from ..transport.redis import RedisTransport
from ..models import Notification
from ..exceptions import TransientNotificationProviderError


class InAppProvider:

    @staticmethod
    def send(notification: Notification, title: str, body: str) -> str:
        channel = f"notification:user:{notification.user_id}"

        message = json.dumps(
            {
                "id": str(notification.id),
                "event_type": notification.event_type,
                "title": title,
                "body": body,
                "payload": notification.payload,
            }
        )

        try:
            RedisTransport.publish(
                channel=channel,
                message=message,
            )
        except Exception as exc:
            raise TransientNotificationProviderError("Failed to send in-app notification") from exc

        return str(notification.id)
