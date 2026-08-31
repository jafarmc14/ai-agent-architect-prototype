from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.prompts import prompt_registry  # noqa: E402
from core.repositories.prompt_repository import PromptRepository  # noqa: E402


def main() -> int:
    repository = PromptRepository()
    for prompt in prompt_registry.versions():
        repository.upsert_prompt_version(prompt)
        print(f"Synced prompt {prompt.prompt_id}_{prompt.version} ({prompt.status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
