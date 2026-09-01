import os
from pathlib import Path
import sys

from streamlit.testing.v1 import AppTest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_development_sidebar_renders_token_usage_panel():
    original_environment = os.environ.get("APP_ENV")
    os.environ["APP_ENV"] = "development"
    try:
        app = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=20).run()
        assert not app.exception
        assert "Token Usage" in [header.value for header in app.sidebar.header]
        assert "No request metrics yet." in [caption.value for caption in app.sidebar.caption]

        app.chat_input[0].set_value("What is the recipe for Korean chicken?").run()
        assert not app.exception
        assert any("only help with store" in markdown.value for markdown in app.markdown)
        assert any("0 LLM calls" in success.value for success in app.sidebar.success)
    finally:
        if original_environment is None:
            os.environ.pop("APP_ENV", None)
        else:
            os.environ["APP_ENV"] = original_environment

if __name__ == "__main__":
    test_development_sidebar_renders_token_usage_panel()
    print("App token sidebar tests passed.")
