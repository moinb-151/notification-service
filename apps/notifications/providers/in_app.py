import json
from ..transport.redis import RedisTransport
from ..models import Notification


class InAppProvider:

    @staticmethod
    def send(notification: Notification) -> str:
        channel = f"notification:user:{notification.user_id}"

        message = json.dumps(
            {
                "id": str(notification.id),
                "event_type": notification.event_type,
                "payload": notification.payload,
            }
        )

        RedisTransport.publish(
            channel=channel,
            message=message,
        )

        return str(notification.id)
