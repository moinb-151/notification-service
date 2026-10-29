from drf_spectacular.extensions import OpenApiAuthenticationExtension


class CustomJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.users.authentication.CustomJWTAuthentication"
    name = ["BearerAuth", "CookieAuth"]

    def get_security_definition(self, auto_schema):
        return [
            {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": (
                    "Send the access JWT in the Authorization header as "
                    "`Bearer <token>`. If this header is present, cookie "
                    "authentication is not attempted."
                ),
            },
            {
                "type": "apiKey",
                "in": "cookie",
                "name": "access_token",
                "description": (
                    "Send the access JWT in the `access_token` cookie. This "
                    "is used only when the Authorization header is absent."
                ),
            },
        ]

    def get_security_requirement(self, auto_schema):
        return [{"BearerAuth": []}, {"CookieAuth": []}]
