from django.urls import path

from .views import AuthView, LoginView, LogoutView, RefreshView, UserRegistrationView

urlpatterns = [
    path("register/", UserRegistrationView.as_view(), name="user-registration"),
    path("login/", LoginView.as_view(), name="user-login"),
    path("refresh/", RefreshView.as_view(), name="token-refresh"),
    path("test/", AuthView.as_view(), name="auth-view"),
    path("logout/", LogoutView.as_view(), name="user-logout"),
]
