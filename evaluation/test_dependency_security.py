import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_python_lockfile_is_exactly_pinned():
    lines = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    requirements = [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]
    assert requirements
    assert all(re.search(r"==[A-Za-z0-9.+_-]+$", line) for line in requirements)


def test_npm_direct_dependencies_are_exactly_pinned():
    package = (ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
    assert '"next": "15.5.25"' in package
    assert '"react": "19.2.8"' in package
    assert '"postcss": "8.5.28"' in package
    assert "^" not in package


def test_external_docker_images_are_digest_pinned():
    files = [
        ROOT / "Dockerfile",
        ROOT / "frontend" / "Dockerfile",
        ROOT / "docker-compose.dev.yml",
        ROOT / "docker-compose.prod.yml",
        ROOT / "docker-compose.postgres.yml",
    ]
    for path in files:
        content = path.read_text(encoding="utf-8")
        for line in content.splitlines():
            if re.search(r"\bimage:", line) and not re.search(r"ai-agent", line):
                assert "@sha256:" in line, f"Unpinned image in {path}: {line}"
            elif re.search(r"^FROM ", line) and not line.startswith("FROM dependencies"):
                assert "@sha256:" in line, f"Unpinned image in {path}: {line}"


if __name__ == "__main__":
    test_python_lockfile_is_exactly_pinned()
    test_npm_direct_dependencies_are_exactly_pinned()
    test_external_docker_images_are_digest_pinned()
    print("Dependency security tests passed.")
