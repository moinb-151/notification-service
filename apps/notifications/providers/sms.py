import requests
from django.conf import settings


class SMSProvider:
    @staticmethod
    def send(phone_number: str, message: str) -> str:
        url = f"{settings.FAST2SMS_BASE_URL}/dev/bulkV2"

        headers = {
            "accept": "application/json",
            "Authorization": settings.FAST2SMS_API_KEY,
            "content-type": "application/json",
        }

        body = {
            "route": "q",
            "message": message,
            "numbers": phone_number,
        }

        response = requests.post(url, json=body, headers=headers)

        data = response.json()

        if data.get("return", ""):
            return data.get("request_id", "")