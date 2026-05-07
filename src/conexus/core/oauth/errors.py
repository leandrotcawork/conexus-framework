class OAuthError(Exception):
    pass


class TokenExpiredError(OAuthError):
    pass


class NeedsAuthError(Exception):
    """Typed pause event — handler renders magic link, conversation suspends."""

    def __init__(self, server_url: str, scopes: list[str], resource: str | None = None):
        super().__init__(f"auth required for {server_url}")
        self.server_url = server_url
        self.scopes = scopes
        self.resource = resource or server_url
