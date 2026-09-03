import logging
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from configs import secrets
from configs import get_settings
from core.auth.jwt import create_session_token, verify_session_token


def test_secret_file_access_does_not_log_value():
    with tempfile.TemporaryDirectory() as directory:
        original_dir = secrets.SECRET_DIR
        secrets.SECRET_DIR = Path(directory)
        try:
            (Path(directory) / "api_key").write_text("super-secret-value", encoding="utf-8")
            records = []
            handler = logging.Handler()
            handler.emit = records.append
            logger = secrets.LOGGER
            logger.addHandler(handler)
            try:
                assert secrets.get_secret("API_KEY") == "super-secret-value"
            finally:
                logger.removeHandler(handler)
            assert records
            assert "super-secret-value" not in records[0].getMessage()
            assert "API_KEY" in records[0].getMessage()
            assert "docker_file" in records[0].getMessage()
        finally:
            secrets.SECRET_DIR = original_dir


def test_secret_environment_precedes_file_without_logging_value():
    with tempfile.TemporaryDirectory() as directory:
        original_dir = secrets.SECRET_DIR
        old_value = os.environ.get("API_KEY")
        secrets.SECRET_DIR = Path(directory)
        os.environ["API_KEY"] = "environment-secret-value"
        try:
            (Path(directory) / "api_key").write_text("file-secret-value", encoding="utf-8")
            assert secrets.get_secret("API_KEY") == "environment-secret-value"
        finally:
            secrets.SECRET_DIR = original_dir
            if old_value is None:
                os.environ.pop("API_KEY", None)
            else:
                os.environ["API_KEY"] = old_value


def test_jwt_previous_key_remains_verifiable_during_rotation():
    names = ("JWT_SECRET_CURRENT", "JWT_SECRET_PREVIOUS")
    original = {name: os.environ.get(name) for name in names}
    try:
        os.environ["JWT_SECRET_CURRENT"] = "old-jwt-secret"
        os.environ.pop("JWT_SECRET_PREVIOUS", None)
        get_settings.cache_clear()
        old_token = create_session_token("user", "user@example.local", "User")

        os.environ["JWT_SECRET_CURRENT"] = "new-jwt-secret"
        os.environ["JWT_SECRET_PREVIOUS"] = "old-jwt-secret"
        get_settings.cache_clear()
        assert verify_session_token(old_token)["sub"] == "user"
        new_token = create_session_token("user", "user@example.local", "User")
        assert verify_session_token(new_token)["sub"] == "user"
    finally:
        for name, value in original.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        get_settings.cache_clear()


if __name__ == "__main__":
    test_secret_file_access_does_not_log_value()
    test_secret_environment_precedes_file_without_logging_value()
    test_jwt_previous_key_remains_verifiable_during_rotation()
    print("Secrets management tests passed.")
