import logging
import os
from pathlib import Path


LOGGER = logging.getLogger("security.secrets")
LOGGER.setLevel(logging.INFO)
SECRET_DIR = Path("/run/secrets")


def get_secret(
    name: str,
    *,
    aliases: tuple[str, ...] = (),
    default: str = "",
    required: bool = False,
) -> str:
    """Read a secret without ever logging its value."""
    for environment_name in (name, *aliases):
        value = os.getenv(environment_name)
        if value:
            _audit_access(name, "environment")
            return value.strip()

    for file_name in (name.lower(), *(alias.lower() for alias in aliases)):
        path = SECRET_DIR / file_name
        try:
            value = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            continue
        if value:
            _audit_access(name, "docker_file")
            return value

    if default:
        _audit_access(name, "development_default")
        return default

    if required:
        raise RuntimeError(f"Required secret {name} is not configured.")
    _audit_access(name, "missing")
    return ""


def _audit_access(name: str, source: str) -> None:
    # Metadata-only audit: values and fingerprints are intentionally excluded.
    LOGGER.info("secret_access name=%s source=%s", name, source)
