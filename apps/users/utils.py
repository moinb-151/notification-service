from django.conf import settings


def _set_auth_cookie(response, key, value, max_age, path="/"):
    response.set_cookie(
        key=key,
        value=value,
        httponly=settings.SIMPLE_JWT.get("AUTH_COOKIE_HTTP_ONLY", True),
        secure=settings.SIMPLE_JWT.get("AUTH_COOKIE_SECURE", not settings.DEBUG),
        samesite=settings.SIMPLE_JWT.get("AUTH_COOKIE_SAMESITE", "Strict"),
        domain=settings.SIMPLE_JWT.get("AUTH_COOKIE_DOMAIN", None),
        max_age=max_age,
        path=path,
    )
