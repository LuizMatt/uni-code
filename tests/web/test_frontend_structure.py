import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
WEB_DIR = ROOT / "web"


def test_web_package_and_typescript_structure_exists() -> None:
    assert (WEB_DIR / "package.json").is_file()
    pkg = json.loads((WEB_DIR / "package.json").read_text(encoding="utf-8"))
    assert "react" in pkg["dependencies"]
    assert "react-router-dom" in pkg["dependencies"]
    assert "build" in pkg["scripts"]

    expected_files = [
        "tsconfig.json",
        "vite.config.ts",
        "tailwind.config.js",
        "postcss.config.js",
        "index.html",
        "README.md",
        "src/main.tsx",
        "src/App.tsx",
        "src/index.css",
        "src/api/types.ts",
        "src/api/client.ts",
        "src/context/AuthContext.tsx",
        "src/components/Layout.tsx",
        "src/components/StatusBadge.tsx",
        "src/components/CodeModal.tsx",
        "src/pages/LoginPage.tsx",
        "src/pages/OverviewPage.tsx",
        "src/pages/StudentsPage.tsx",
        "src/pages/StudentDetailPage.tsx",
        "src/pages/UnitDetailPage.tsx",
    ]
    for rel in expected_files:
        assert (WEB_DIR / rel).is_file(), f"Missing frontend file: web/{rel}"


def test_web_readme_documents_all_frontend_and_api_routes() -> None:
    readme = (WEB_DIR / "README.md").read_text(encoding="utf-8")
    for frontend_route in [
        "/login",
        "/",
        "/alunos",
        "/alunos/:matricula",
        "/unidades/:codigo",
    ]:
        assert frontend_route in readme

    for api_route in [
        "/api/auth/me",
        "/api/overview",
        "/api/students",
        "/api/students/{registration}",
        "/api/units/{code}",
        "/api/export.csv",
    ]:
        assert api_route in readme

