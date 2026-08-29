import requests
from django.conf import settings
from ..exceptions import (
    NotificationProviderError,
    TransientNotificationProviderError,
    PermanentNotificationProviderError,
)


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

        try:
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
        except requests.Timeout as exc:
            raise TransientNotificationProviderError(
                "Fast2SMS request timed out."
            ) from exc

        except requests.ConnectionError as exc:
            raise TransientNotificationProviderError(
                "Unable to connect to Fast2SMS."
            ) from exc

        except requests.HTTPError as exc:
            status_code = exc.response.status_code

            if status_code == 429 or status_code >= 500:
                raise TransientNotificationProviderError(
                    f"Fast2SMS returned HTTP {status_code}."
                ) from exc

            raise PermanentNotificationProviderError(
                f"Fast2SMS returned HTTP {status_code}."
            ) from exc
