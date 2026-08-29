class NotificationProviderError(Exception):
    """Base exception for notification provider errors."""


class TransientNotificationProviderError(NotificationProviderError):
    """Provider error that may succeed if retried."""


class PermanentNotificationProviderError(NotificationProviderError):
    """Provider error that should not be retried."""
