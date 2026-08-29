import boto3
from django.conf import settings
from botocore.exceptions import BotoCoreError, ClientError
from ..exceptions import (
    TransientNotificationProviderError,
    PermanentNotificationProviderError,
)


class EmailProvider:
    _client = boto3.client(
        "ses",
        settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )

    @classmethod
    def send(cls, to: str, subject: str, body: str) -> str:
        try:
            response = cls._client.send_email(
                Source=settings.SES_FROM_EMAIL,
                Destination={
                    "ToAddresses": [to],
                },
                Message={
                    "Subject": {
                        "Data": subject,
                        "Charset": "UTF-8",
                    },
                    "Body": {
                        "Html": {
                            "Data": body,
                            "Charset": "UTF-8",
                        },
                    },
                },
            )

            return response["MessageId"]
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in (
                "Throttling",
                "ThrottlingException",
                "TooManyRequestsException",
            ):
                raise TransientNotificationProviderError(
                    f"SES throttling error: {error_code}"
                ) from exc

            raise PermanentNotificationProviderError(f"SES error: {error_code}")
        except BotoCoreError as exc:
            raise TransientNotificationProviderError(
                f"SES provider error: {exc}"
            ) from exc
