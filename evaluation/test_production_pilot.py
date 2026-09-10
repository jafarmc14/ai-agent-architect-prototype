import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.services.pilot_access import require_pilot_access


def test_membership_is_explicit_and_tenant_scoped():
    settings = SimpleNamespace(pilot_enabled=True, pilot_allowed_accounts="store:alice")
    with patch("core.services.pilot_access.get_settings", return_value=settings):
        for token, claims, allowed in [
            (None, {}, False),
            ("valid", {"sub": "alice", "tenant_id": "store"}, True),
            ("valid", {"sub": "alice", "tenant_id": "other"}, False),
            ("valid", {"sub": "bob", "tenant_id": "store", "role": "admin"}, False),
        ]:
            with patch("core.services.pilot_access.verify_session_token", return_value=claims):
                try:
                    require_pilot_access(token)
                    assert allowed
                except PermissionError:
                    assert not allowed
        settings.pilot_allowed_accounts = ""
        with patch("core.services.pilot_access.verify_session_token", return_value={"sub": "alice", "tenant_id": "store"}):
            try:
                require_pilot_access("valid")
                raise AssertionError("Empty allowlist must deny access")
            except PermissionError:
                pass
        settings.pilot_enabled = False
        require_pilot_access(None)


def test_api_feedback_and_report_authorization():
    from fastapi.testclient import TestClient
    import api.main as main

    settings = SimpleNamespace(database_provider="postgres", api_cors_origins="", pilot_enabled=False)
    claims = {"sub": str(uuid4()), "tenant_id": "store", "role": "customer"}
    with patch.object(main, "get_settings", return_value=settings), \
         patch.object(main, "verify_session_token", return_value=claims), \
         patch.object(main, "require_pilot_access"), \
         patch.object(main, "PilotRepository") as repository:
        client = TestClient(main.create_app())
        request_id = str(uuid4())
        body = {"request_id": request_id, "kind": "thumbs_up"}
        headers = {"Authorization": "Bearer valid"}
        assert client.post("/api/v1/feedback", json=body).status_code == 401
        assert client.get("/api/v1/pilot/usage", headers=headers).status_code == 403
        repository.return_value.feedback.return_value = {"status": "saved"}
        assert client.post("/api/v1/feedback", json=body, headers=headers).status_code == 200
        repository.return_value.feedback.assert_called_once_with(request_id, "store", claims["sub"], "thumbs_up")
        assert client.post("/api/v1/feedback", json={**body, "tenant_id": "other"}, headers=headers).status_code == 422
        assert client.post("/api/v1/feedback", json={**body, "kind": "execute_tool"}, headers=headers).status_code == 422
        repository.return_value.feedback.side_effect = LookupError()
        assert client.post("/api/v1/feedback", json=body, headers=headers).status_code == 404
        claims["role"] = "manager"
        repository.return_value.usage.return_value = {"daily": [], "models": [], "feedback": []}
        assert client.get("/api/v1/pilot/usage?days=7", headers=headers).status_code == 200
        repository.return_value.usage.assert_called_once_with("store", 7)
        assert client.get("/api/v1/pilot/usage?days=1000", headers=headers).status_code == 422


def test_pilot_rejection_precedes_chat_execution():
    from fastapi.testclient import TestClient
    import api.main as main
    from core.orchestration.runtime import _context_from_token

    with patch.object(main, "require_pilot_access", side_effect=PermissionError("Not invited")), \
         patch.object(main.chat_application_service, "chat") as chat:
        response = TestClient(main.create_app()).post("/api/v1/chat", json={"message": "Hi"})
        assert response.status_code == 403
        chat.assert_not_called()
    with patch("core.services.pilot_access.require_pilot_access", side_effect=PermissionError("Not invited")):
        try:
            _context_from_token(None)
            raise AssertionError("Direct runtime bypassed pilot access")
        except PermissionError:
            pass


if __name__ == "__main__":
    test_membership_is_explicit_and_tenant_scoped()
    test_api_feedback_and_report_authorization()
    test_pilot_rejection_precedes_chat_execution()
    print("Production pilot tests passed.")
