import os
import sys
from contextlib import contextmanager
from types import SimpleNamespace
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-login-tests")


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.main import create_app  # noqa: E402
from core.auth.login_throttle import LoginThrottle, login_throttle  # noqa: E402
from core.auth.password import hash_password, verify_password  # noqa: E402


def _fake_settings():
    return SimpleNamespace(database_provider="postgres", api_cors_origins="*")


class _FakeUserRepository:
    def __init__(self, user: dict | None = None):
        self.user = user

    def find_login_user(self, email: str):
        if self.user and email == self.user["email"]:
            return self.user
        return None


@contextmanager
def _patched(repository, settings=None):
    import api.main as main

    original_repository = main._user_repository
    original_settings = main.get_settings
    main._user_repository = repository
    main.get_settings = lambda: settings if settings is not None else _fake_settings()
    try:
        yield create_app()
    finally:
        main._user_repository = original_repository
        main.get_settings = original_settings


def _post_login(app, username, password):
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def _demo_user(password_hash: str) -> dict:
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "email": "admin@example.local",
        "name": "Admin",
        "password_hash": password_hash,
        "metadata": {"role": "admin", "tenant_id": "default"},
    }


def test_password_hash_roundtrip():
    password_hash = hash_password("S3cret-Pass")
    assert verify_password("S3cret-Pass", password_hash) is True
    assert verify_password("wrong-pass", password_hash) is False
    assert verify_password("anything", None) is False
    assert verify_password("anything", "") is False


def test_throttle_locks_after_max_failures():
    throttle = LoginThrottle(max_failures=3, lockout_seconds=60, ip_max_failures=100)
    throttle.reset()
    assert throttle.check("user@example.local", "1.2.3.4") is None
    throttle.record_failure("user@example.local", "1.2.3.4")
    throttle.record_failure("user@example.local", "1.2.3.4")
    throttle.record_failure("user@example.local", "1.2.3.4")
    retry_after = throttle.check("user@example.local", "1.2.3.4")
    assert retry_after is not None
    assert retry_after <= 61


def test_throttle_success_resets_lockout():
    throttle = LoginThrottle(max_failures=2, lockout_seconds=60, ip_max_failures=100)
    throttle.reset()
    throttle.record_failure("a@example.local", "1.2.3.4")
    throttle.record_failure("a@example.local", "1.2.3.4")
    assert throttle.check("a@example.local", "1.2.3.4") is not None
    throttle.record_success("a@example.local")
    assert throttle.check("a@example.local", "1.2.3.4") is None


def test_throttle_per_ip_window():
    throttle = LoginThrottle(max_failures=100, lockout_seconds=60, ip_max_failures=2, ip_window_seconds=3600)
    throttle.reset()
    throttle.record_failure("u1@example.local", "9.9.9.9")
    throttle.record_failure("u2@example.local", "9.9.9.9")
    assert throttle.check("u3@example.local", "9.9.9.9") is not None
    assert throttle.check("u3@example.local", "8.8.8.8") is None


def test_login_success_returns_token():
    login_throttle.reset()
    with _patched(_FakeUserRepository(_demo_user(hash_password("correct-horse")))) as app:
        response = _post_login(app, "admin@example.local", "correct-horse")
    assert response.status_code == 200
    body = response.json()
    assert body["token"]
    assert body["user"]["email"] == "admin@example.local"


def test_login_rejects_with_generic_message():
    login_throttle.reset()
    with _patched(_FakeUserRepository(_demo_user(hash_password("right-password")))) as app:
        wrong_password = _post_login(app, "admin@example.local", "wrong-password")
        no_user = _post_login(app, "ghost@example.local", "anything")
    assert wrong_password.status_code == 401
    assert no_user.status_code == 401
    assert wrong_password.json()["detail"] == no_user.json()["detail"] == "Invalid username or password."


def test_login_locked_after_repeated_failures():
    login_throttle.reset()
    with _patched(_FakeUserRepository(_demo_user(hash_password("right-password")))) as app:
        for _ in range(5):
            response = _post_login(app, "admin@example.local", "wrong-password")
            assert response.status_code == 401
        blocked = _post_login(app, "admin@example.local", "right-password")
    assert blocked.status_code == 429
    assert blocked.headers.get("Retry-After") is not None


if __name__ == "__main__":
    test_password_hash_roundtrip()
    test_throttle_locks_after_max_failures()
    test_throttle_success_resets_lockout()
    test_throttle_per_ip_window()
    test_login_success_returns_token()
    test_login_rejects_with_generic_message()
    test_login_locked_after_repeated_failures()
    print("Login security tests passed.")