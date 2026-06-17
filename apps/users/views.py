from django.conf import settings
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import User
from .serializers import LoginSerializer, UserRegistrationSerializer
from .utils import _set_auth_cookie


class UserRegistrationView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(TokenObtainPairView):
    permission_classes = [permissions.AllowAny]
    serializer_class = LoginSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            data = serializer.validated_data
            refresh = data.pop("refresh")
            access = data.pop("access")

            response = Response(data)

            _set_auth_cookie(
                response=response,
                key="access_token",
                value=access,
                max_age=settings.SIMPLE_JWT.get(
                    "ACCESS_TOKEN_LIFETIME"
                ).total_seconds(),
            )

            _set_auth_cookie(
                response=response,
                key="refresh_token",
                value=refresh,
                max_age=settings.SIMPLE_JWT.get(
                    "REFRESH_TOKEN_LIFETIME"
                ).total_seconds(),
            )

            return response

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RefreshView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        refresh_token = request.COOKIES.get("refresh_token")

        if not refresh_token:
            return Response(
                {"detail": "Refresh token not found"}, status=status.HTTP_404_NOT_FOUND
            )

        try:
            old_refresh_token = RefreshToken(refresh_token)
            user_id = old_refresh_token.get("user_id")
            old_refresh_token.blacklist()
        except TokenError:
            return Response(
                {"detail": "Invalid or expired refresh token"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {"detail": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

        new_refresh_token = RefreshToken.for_user(user)
        access_token = str(new_refresh_token.access_token)

        response = Response(
            {"message": "Token refreshed successfully"}, status=status.HTTP_200_OK
        )

        _set_auth_cookie(
            response=response,
            key="access_token",
            value=access_token,
            max_age=settings.SIMPLE_JWT.get("ACCESS_TOKEN_LIFETIME").total_seconds(),
        )

        _set_auth_cookie(
            response=response,
            key="refresh_token",
            value=str(new_refresh_token),
            max_age=settings.SIMPLE_JWT.get("REFRESH_TOKEN_LIFETIME").total_seconds(),
        )

        return response


class LogoutView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        refresh_token = request.COOKIES.get("refresh_token")

        response = Response(
            {"message": "Successfully logged out."}, status=status.HTTP_200_OK
        )

        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except TokenError:
                pass

        for key in ("refresh_token", "access_token"):
            response.delete_cookie(
                key=key,
                path="/",
                samesite="Strict",
            )

        return response


class AuthView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response({"message": "Welcome"})
