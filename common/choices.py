from django.db import models


class ChannelType(models.TextChoices):
    EMAIL = "email", "Email"
    SMS = "sms", "SMS"
    IN_APP = "in_app", "In-App"
