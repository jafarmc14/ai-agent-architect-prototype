from pathlib import Path
import importlib.util
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_fastapi_dependency_declared():
    requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "fastapi" in requirements
    assert "uvicorn" in requirements


def test_api_contract_files_exist():
    api_dir = PROJECT_ROOT / "api"
    expected_files = {
        "__init__.py",
        "main.py",
        "schemas.py",
        "services.py",
        "client.py",
    }
    assert expected_files.issubset({path.name for path in api_dir.iterdir()})


def test_streamlit_can_run_as_api_client():
    app_source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    settings_source = (PROJECT_ROOT / "configs" / "settings.py").read_text(encoding="utf-8")
    env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "AgentAPIClient" in app_source
    assert "STREAMLIT_API_CLIENT_ENABLED=false" in env_example
    assert "streamlit_api_client_enabled" in settings_source
    assert "api_base_url" in settings_source


def test_api_cors_for_next_frontend():
    main_source = (PROJECT_ROOT / "api" / "main.py").read_text(encoding="utf-8")
    settings_source = (PROJECT_ROOT / "configs" / "settings.py").read_text(encoding="utf-8")
    env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "CORSMiddleware" in main_source
    assert "api_cors_origins" in settings_source
    assert "API_CORS_ORIGINS" in env_example
    assert "http://localhost:3000" in env_example


def test_fastapi_routes_when_dependency_available():
    if importlib.util.find_spec("fastapi") is None:
        return

    from api.main import app

    routes = {route.path for route in app.routes}
    assert "/health" in routes
    assert "/api/v1/config" in routes
    assert "/api/v1/config/llm" in routes
    assert "/api/v1/chat" in routes


if __name__ == "__main__":
    test_fastapi_dependency_declared()
    test_api_contract_files_exist()
    test_streamlit_can_run_as_api_client()
    test_api_cors_for_next_frontend()
    test_fastapi_routes_when_dependency_available()
    print("API architecture tests passed.")
