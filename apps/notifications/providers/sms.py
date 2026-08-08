import requests
from django.conf import settings


class NotificationProviderError(Exception):
    pass


class SMSProvider:
    @staticmethod
    def send(phone_number: str, message: str) -> str:
        url = f"{settings.FAST2SMS_BASE_URL}/dev/bulkV2"

        headers = {
            "accept": "application/json",
            "Authorization": settings.FAST2SMS_API_KEY,
            "content-type": "application/json",
        }

        payload = {
            "route": "q",
            "message": message,
            "numbers": phone_number,
        }

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()

        data = response.json()

        if not data.get("return"):
            raise NotificationProviderError(
                ", ".join(data.get("message", ["Unknown Fast2SMS error"]))
            )

        return data["request_id"]
