from configs import get_settings
from core.auth.jwt import verify_session_token


def require_pilot_access(token: str | None) -> None:
    settings = get_settings()
    if not settings.pilot_enabled:
        return
    if not token:
        raise PermissionError("Pilot access requires an invited account.")
    claims = verify_session_token(token)
    allowed = {entry.strip() for entry in settings.pilot_allowed_accounts.split(",") if entry.strip()}
    account = f"{claims.get('tenant_id', 'default')}:{claims['sub']}"
    if account not in allowed:
        raise PermissionError("This account is not enrolled in the pilot.")
