import boto3
from django.conf import settings


class EmailProvider:
    _client = boto3.client(
        "ses",
        settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )

    @classmethod
    def send(cls, to: str, subject: str, body: str) -> str:
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
