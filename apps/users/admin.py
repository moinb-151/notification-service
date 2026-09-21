from django.contrib import admin
from .models import User, NotificationPreference

admin.site.register(User)
admin.site.register(NotificationPreference)
