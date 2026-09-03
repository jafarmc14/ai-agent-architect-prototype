import base64
import hashlib
import hmac
import json
import time
from typing import Any

from configs import get_settings


class AuthError(ValueError):
    pass


def create_session_token(
    user_id: str,
    email: str,
    name: str,
    role: str = "customer",
    tenant_id: str = "default",
    expires_in_seconds: int = 24 * 60 * 60,
) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "email": email,
        "name": name,
        "role": role,
        "tenant_id": tenant_id,
        "iat": now,
        "exp": now + expires_in_seconds,
    }
    signing_input = f"{_b64_json(header)}.{_b64_json(payload)}"
    signature = _sign(signing_input, get_settings().jwt_secret)
    return f"{signing_input}.{signature}"


def verify_session_token(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthError("Invalid session token format.")

    signing_input = f"{parts[0]}.{parts[1]}"
    settings = get_settings()
    signatures = [_sign(signing_input, settings.jwt_secret)]
    if settings.jwt_secret_previous:
        signatures.append(_sign(signing_input, settings.jwt_secret_previous))
    if not any(hmac.compare_digest(parts[2], signature) for signature in signatures):
        raise AuthError("Invalid session token signature.")

    payload = json.loads(_b64_decode(parts[1]).decode("utf-8"))
    exp = int(payload.get("exp", 0))
    if exp <= int(time.time()):
        raise AuthError("Session token has expired.")
    if not payload.get("sub"):
        raise AuthError("Session token is missing subject.")
    return payload


def _sign(signing_input: str, secret: str) -> str:
    if not secret:
        raise AuthError("JWT signing secret is not configured.")
    digest = hmac.new(secret.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256).digest()
    return _b64_bytes(digest)


def _b64_json(value: dict[str, Any]) -> str:
    return _b64_bytes(json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _b64_bytes(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
