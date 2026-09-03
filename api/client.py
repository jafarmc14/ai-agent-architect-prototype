import json
import urllib.error
import urllib.request
from typing import Any


class AgentAPIClientError(RuntimeError):
    pass


class AgentAPIClient:
    def __init__(self, base_url: str, timeout_seconds: int = 120) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def get_config(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/config")

    def configure_llm(self, provider: str, model: str | None = None) -> dict[str, Any]:
        return self._request("POST", "/api/v1/config/llm", {"provider": provider, "model": model})

    def chat(self, message: str, *, auth_token: str | None, session_id: str) -> dict[str, Any]:
        payload = {
            "message": message,
            "auth_token": auth_token,
            "session_id": session_id,
        }
        return self._request("POST", "/api/v1/chat", payload)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise AgentAPIClientError(f"API request failed with HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise AgentAPIClientError(f"API is not reachable at {self.base_url}: {exc.reason}") from exc
