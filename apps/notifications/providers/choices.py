from common.choices import ChannelType

from .email import EmailProvider
from .sms import SMSProvider

PROVIDERS = {
    ChannelType.EMAIL: EmailProvider,
    ChannelType.SMS: SMSProvider,
}
