from rest_framework import serializers


class ErrorDetailSerializer(serializers.Serializer):
    detail = serializers.CharField()


class MessageResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
