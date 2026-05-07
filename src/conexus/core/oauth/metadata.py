from dataclasses import dataclass, field
from urllib.parse import urljoin
import httpx


@dataclass
class ProtectedResourceMetadata:
    resource: str
    authorization_servers: list[str]


@dataclass
class AuthorizationServerMetadata:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str | None = None
    code_challenge_methods_supported: list[str] = field(default_factory=list)
    scopes_supported: list[str] = field(default_factory=list)


async def discover_protected_resource(server_url: str) -> ProtectedResourceMetadata:
    url = urljoin(server_url.rstrip("/") + "/", ".well-known/oauth-protected-resource")
    async with httpx.AsyncClient() as c:
        r = await c.get(url, timeout=10.0)
        r.raise_for_status()
        d = r.json()
    return ProtectedResourceMetadata(resource=d["resource"],
                                      authorization_servers=d["authorization_servers"])


async def discover_authorization_server(as_url: str) -> AuthorizationServerMetadata:
    url = urljoin(as_url.rstrip("/") + "/", ".well-known/oauth-authorization-server")
    async with httpx.AsyncClient() as c:
        r = await c.get(url, timeout=10.0)
        r.raise_for_status()
        d = r.json()
    return AuthorizationServerMetadata(
        issuer=d["issuer"],
        authorization_endpoint=d["authorization_endpoint"],
        token_endpoint=d["token_endpoint"],
        registration_endpoint=d.get("registration_endpoint"),
        code_challenge_methods_supported=d.get("code_challenge_methods_supported", []),
        scopes_supported=d.get("scopes_supported", []),
    )
