import redis
import redis.asyncio as aioredis
from django.conf import settings


class RedisTransport:
    _client = redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )

    _async_client = aioredis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )

    @classmethod
    def publish(cls, channel: str, message: str) -> int:
        return cls._client.publish(channel, message)

    @classmethod
    def subscribe(cls, channel: str):
        pubsub = cls._client.pubsub()
        pubsub.subscribe(channel)
        return pubsub

    @classmethod
    async def async_subscribe(cls, channel: str):
        pubsub = cls._async_client.pubsub()
        await pubsub.subscribe(channel)
        return pubsub
