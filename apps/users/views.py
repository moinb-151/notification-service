from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import User
from .serializers import (
    LoginSerializer,
    LoginResponseSerializer,
    PublicUserSerializer,
    UserRegistrationSerializer,
    UserProfileSerializer,
)
from .utils import _set_auth_cookie
from common.serializers import ErrorDetailSerializer, MessageResponseSerializer


class UserRegistrationView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        operation_id="user_registration_create",
        request=UserRegistrationSerializer,
        responses={
            201: PublicUserSerializer,
            400: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="Field-keyed validation errors.",
            ),
            401: ErrorDetailSerializer,
            403: ErrorDetailSerializer,
        },
    )
    def post(self, request):
        if not settings.ENABLE_SIGNUPS:
            return Response(
                {"detail": "Signups are currently disabled"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(TokenObtainPairView):
    permission_classes = [permissions.AllowAny]
    serializer_class = LoginSerializer

    @extend_schema(
        operation_id="user_login_create",
        request=LoginSerializer,
        responses={
            200: LoginResponseSerializer,
            400: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="Field-keyed validation errors.",
            ),
            401: ErrorDetailSerializer,
        },
        description=(
            "Authenticates a user using their email and password. "
            "On successful authentication, sets the access and refresh "
            "tokens in HTTP cookies and returns the user's information."
        ),
    )
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


class UserProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="user_profile_retrieve",
        request=None,
        responses={200: UserProfileSerializer, 401: ErrorDetailSerializer},
    )
    def get(self, request):
        user = request.user
        serializer = UserProfileSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="user_profile_update",
        request=UserProfileSerializer,
        responses={
            200: UserProfileSerializer,
            400: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="Field-keyed validation errors.",
            ),
            401: ErrorDetailSerializer,
        },
    )
    def patch(self, request):
        user = request.user
        serializer = UserProfileSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RefreshView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        operation_id="token_refresh",
        auth=[{"BearerAuth": []}, {"CookieAuth": []}, {}],
        request=None,
        parameters=[
            OpenApiParameter(
                name="refresh_token",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.COOKIE,
                required=True,
                description=(
                    "Refresh JWT cookie required to complete token refresh. "
                    "This is separate from the optional access-token cookie "
                    "used for request authentication."
                ),
            )
        ],
        responses={
            200: MessageResponseSerializer,
            401: ErrorDetailSerializer,
            404: ErrorDetailSerializer,
        },
    )
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

    @extend_schema(
        operation_id="user_logout",
        auth=[{"BearerAuth": []}, {"CookieAuth": []}, {}],
        request=None,
        parameters=[
            OpenApiParameter(
                name="refresh_token",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.COOKIE,
                required=False,
                description=(
                    "Optional refresh JWT cookie to blacklist. This is separate "
                    "from the optional access-token cookie used for request "
                    "authentication."
                ),
            )
        ],
        responses={
            200: MessageResponseSerializer,
            401: ErrorDetailSerializer,
        },
    )
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

    @extend_schema(
        operation_id="auth_test_retrieve",
        request=None,
        responses={200: MessageResponseSerializer, 401: ErrorDetailSerializer},
    )
    def get(self, request):
        return Response({"message": "Welcome"})
