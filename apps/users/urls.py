from django.urls import path

from .views import LoginView, RefreshView, UserRegistrationView

urlpatterns = [
    path("register/", UserRegistrationView.as_view(), name="user-registration"),
    path("login/", LoginView.as_view(), name="user-login"),
    path("refresh/", RefreshView.as_view(), name="token-refresh"),
]
