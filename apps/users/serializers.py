from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from time import perf_counter

from .models import User


class UserRegistrationSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True)
    password_confirmation = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["email", "password", "password_confirmation"]

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirmation"]:
            raise serializers.ValidationError("Passwords do not match.")
        return attrs

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def create(self, validated_data):
        validated_data.pop("password_confirmation")
        return User.objects.create_user(**validated_data)


class PublicUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["email"]
        read_only_fields = fields


class LoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        start = perf_counter()

        data = super().validate(attrs)
        auth_time = perf_counter()

        user_data = UserRegistrationSerializer(self.user).data
        serialization_time = perf_counter()

        data.update({
            "message": "Login successful",
            "user": user_data,
        })

        print(f"Authentication + token generation: {auth_time - start:.3f}s")
        print(f"User serialization: {serialization_time - auth_time:.3f}s")

        return data


class LoginResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    user = PublicUserSerializer(read_only=True)


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "first_name", "last_name", "email", "phone", "created_at", "updated_at"]