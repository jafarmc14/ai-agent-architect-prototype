from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = PROJECT_ROOT / "frontend"


def read_frontend_file(relative_path: str) -> str:
    return (FRONTEND_ROOT / relative_path).read_text(encoding="utf-8")


def test_next_frontend_scaffold_exists():
    expected = {
        "package.json",
        "next.config.mjs",
        "tsconfig.json",
        "tailwind.config.ts",
        "postcss.config.mjs",
        "app/layout.tsx",
        "app/page.tsx",
        "app/globals.css",
        ".env.example",
    }
    existing = {
        str(path.relative_to(FRONTEND_ROOT)).replace("\\", "/")
        for path in FRONTEND_ROOT.rglob("*")
        if path.is_file()
    }
    assert expected.issubset(existing)


def test_frontend_is_api_backed_and_auth_gated():
    page = read_frontend_file("app/page.tsx")
    auth_lib = read_frontend_file("lib/auth.ts")
    assert "NEXT_PUBLIC_API_BASE_URL" in page
    assert "/api/v1/chat" in page
    assert "/api/v1/config" in page
    assert "useEffect" in page
    assert "Authorization" in page
    assert "Bearer" in page
    assert "localStorage" in auth_lib
    assert "localStorage" not in page
    assert "sessionStorage" not in page
    assert "document.cookie" not in page


def test_frontend_visual_language_is_operational():
    css = read_frontend_file("app/globals.css")
    page = read_frontend_file("app/page.tsx")

    assert "@tailwind base" in css
    assert "@tailwind components" in css
    assert "@tailwind utilities" in css
    assert "grid min-h-screen grid-cols-1 xl:grid-cols" in page
    assert "bg-surface-950" in page
    assert "bg-amber-action" in page
    assert "rounded-md" in page
    assert "linear-gradient" not in css
    assert "hero" not in page.lower()
    assert "landing" not in page.lower()


def test_frontend_dependency_manifest():
    manifest = read_frontend_file("package.json")
    assert '"next"' in manifest
    assert '"react"' in manifest
    assert '"lucide-react"' in manifest
    assert '"tailwindcss"' in manifest
    assert '"postcss"' in manifest
    assert '"autoprefixer"' in manifest


if __name__ == "__main__":
    test_next_frontend_scaffold_exists()
    test_frontend_is_api_backed_and_auth_gated()
    test_frontend_visual_language_is_operational()
    test_frontend_dependency_manifest()
    print("Frontend migration tests passed.")
