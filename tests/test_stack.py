from pathlib import Path

from rebrief.parsers.stack import StackParser


def test_empty_repo(tmp_path: Path) -> None:
    result = StackParser(str(tmp_path)).parse()

    assert set(result.keys()) == {
        "languages",
        "manifests",
        "frameworks",
        "dependencies",
        "packages",
        "is_empty",
        "manifest_warnings",
    }
    assert result["languages"] == []
    assert result["manifests"] == []
    assert result["frameworks"] == []
    assert result["dependencies"] == []
    assert result["packages"] == []
    assert result["manifest_warnings"] == []
    assert result["is_empty"] is True


def test_python_requirements(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text(
        "django==4.2\nrequests>=2.28\n# comment\n-r other.txt\n",
        encoding="utf-8",
    )

    result = StackParser(str(tmp_path)).parse()

    assert result["languages"] == ["Python"]
    assert result["manifests"] == ["requirements.txt"]
    assert "django" in result["dependencies"]
    assert "requests" in result["dependencies"]
    assert result["is_empty"] is False


def test_python_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """[project]
name = "demo"
dependencies = [
    "click>=8.1",
    "colorama>=0.4",
]
""",
        encoding="utf-8",
    )

    result = StackParser(str(tmp_path)).parse()

    assert result["languages"] == ["Python"]
    assert result["manifests"] == ["pyproject.toml"]
    assert "click>=8.1" in result["dependencies"]


def test_node_package_json(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        """{
  "dependencies": {
    "react": "^18.0.0"
  },
  "devDependencies": {
    "typescript": "^5.0.0"
  }
}""",
        encoding="utf-8",
    )

    result = StackParser(str(tmp_path)).parse()

    assert result["languages"] == ["JavaScript/TypeScript"]
    assert result["manifests"] == ["package.json"]
    assert "react" in result["dependencies"]
    assert "typescript" in result["dependencies"]


def test_go_mod(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module example.com/demo\n", encoding="utf-8")

    result = StackParser(str(tmp_path)).parse()

    assert result["languages"] == ["Go"]
    assert result["manifests"] == ["go.mod"]


def test_cargo_toml(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "demo"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )

    result = StackParser(str(tmp_path)).parse()

    assert result["languages"] == ["Rust"]
    assert result["manifests"] == ["Cargo.toml"]


def test_framework_signatures(tmp_path: Path) -> None:
    (tmp_path / "manage.py").write_text("# django\n", encoding="utf-8")
    (tmp_path / "vite.config.js").write_text("export default {}\n", encoding="utf-8")

    result = StackParser(str(tmp_path)).parse()

    assert "Django" in result["frameworks"]
    assert "Vite" in result["frameworks"]


def test_next_config_mjs(tmp_path: Path) -> None:
    (tmp_path / "next.config.mjs").write_text("export default {}\n", encoding="utf-8")

    result = StackParser(str(tmp_path)).parse()

    assert result["frameworks"] == ["Next.js"]


def test_combined_stack(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"dependencies": {"react": "^18.0.0"}}',
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["click>=8.1"]\n',
        encoding="utf-8",
    )
    (tmp_path / "manage.py").write_text("# django\n", encoding="utf-8")

    result = StackParser(str(tmp_path)).parse()

    assert "JavaScript/TypeScript" in result["languages"]
    assert "Python" in result["languages"]
    assert "package.json" in result["manifests"]
    assert "pyproject.toml" in result["manifests"]
    assert "Django" in result["frameworks"]
    assert "react" in result["dependencies"]
    assert "click>=8.1" in result["dependencies"]


def test_nested_frontend_package_json(tmp_path: Path) -> None:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text(
        '{"dependencies": {"react": "^18.0.0"}}',
        encoding="utf-8",
    )

    result = StackParser(str(tmp_path)).parse()

    assert result["manifests"] == ["frontend/package.json"]
    assert "React" in result["frameworks"]
    assert "react" in result["dependencies"]


def test_nested_backend_requirements(tmp_path: Path) -> None:
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "requirements.txt").write_text("django==4.2\n", encoding="utf-8")

    result = StackParser(str(tmp_path)).parse()

    assert result["manifests"] == ["backend/requirements.txt"]
    assert "Django" in result["frameworks"]
    assert "django" in result["dependencies"]


def test_nested_next_dependency(tmp_path: Path) -> None:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text(
        '{"dependencies": {"next": "^14.0.0"}}',
        encoding="utf-8",
    )

    result = StackParser(str(tmp_path)).parse()

    assert "Next.js" in result["frameworks"]


def test_djangorestframework_in_requirements(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text(
        "djangorestframework==3.14.0\n",
        encoding="utf-8",
    )

    result = StackParser(str(tmp_path)).parse()

    assert "Django REST Framework" in result["frameworks"]


def test_skips_node_modules(tmp_path: Path) -> None:
    node_modules = tmp_path / "node_modules" / "ignored"
    node_modules.mkdir(parents=True)
    (node_modules / "package.json").write_text(
        '{"dependencies": {"react": "^18.0.0"}}',
        encoding="utf-8",
    )

    result = StackParser(str(tmp_path)).parse()

    assert result["manifests"] == []
    assert "React" not in result["frameworks"]


def test_respects_rebriefignore(tmp_path: Path) -> None:
    custom = tmp_path / "custom_vendor"
    custom.mkdir()
    (custom / "package.json").write_text(
        '{"dependencies": {"react": "^18.0.0"}}',
        encoding="utf-8",
    )
    (tmp_path / ".rebriefignore").write_text("custom_vendor/\n", encoding="utf-8")

    result = StackParser(str(tmp_path)).parse()

    assert result["manifests"] == []
    assert "React" not in result["frameworks"]


def test_depth_limit_excludes_deep_files(tmp_path: Path) -> None:
    deep_dir = tmp_path / "a" / "b" / "c" / "d"
    deep_dir.mkdir(parents=True)
    (deep_dir / "package.json").write_text(
        '{"dependencies": {"react": "^18.0.0"}}',
        encoding="utf-8",
    )

    result = StackParser(str(tmp_path)).parse()

    assert result["manifests"] == []
    assert "React" not in result["frameworks"]


def test_monorepo_all_manifests(tmp_path: Path) -> None:
    frontend = tmp_path / "frontend"
    backend = tmp_path / "backend"
    frontend.mkdir()
    backend.mkdir()
    (frontend / "package.json").write_text('{"dependencies": {}}', encoding="utf-8")
    (backend / "requirements.txt").write_text("django==4.2\n", encoding="utf-8")
    (tmp_path / "go.mod").write_text("module example.com/demo\n", encoding="utf-8")
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "demo"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )

    result = StackParser(str(tmp_path)).parse()

    assert result["manifests"] == [
        "Cargo.toml",
        "backend/requirements.txt",
        "frontend/package.json",
        "go.mod",
    ]
    assert result["languages"] == ["Go", "JavaScript/TypeScript", "Python", "Rust"]
    assert result["is_empty"] is False
    assert "Django" in result["frameworks"]
    assert result["manifest_warnings"] == []


def test_go_mod_dependencies(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text(
        "module example.com/demo\n"
        "go 1.22\n"
        "require github.com/gin-gonic/gin v1.9.0\n",
        encoding="utf-8",
    )

    result = StackParser(str(tmp_path)).parse()

    assert "github.com/gin-gonic/gin" in result["dependencies"]


def test_cargo_toml_dependencies(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "demo"\nversion = "0.1.0"\n'
        '[dependencies]\nserde = "1.0"\naxum = "0.7"\n',
        encoding="utf-8",
    )

    result = StackParser(str(tmp_path)).parse()

    assert "serde" in result["dependencies"]
    assert "axum" in result["dependencies"]


def test_pom_xml_spring_boot_framework(tmp_path: Path) -> None:
    (tmp_path / "pom.xml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>
</project>
""",
        encoding="utf-8",
    )

    result = StackParser(str(tmp_path)).parse()

    assert result["languages"] == ["Java"]
    assert "spring-boot-starter-web" in result["dependencies"]
    assert "Spring Boot" in result["frameworks"]


def test_build_gradle_kts_quarkus(tmp_path: Path) -> None:
    (tmp_path / "build.gradle.kts").write_text(
        'dependencies {\n'
        '    implementation("io.quarkus:quarkus-resteasy-reactive:3.6.0")\n'
        "}\n",
        encoding="utf-8",
    )

    result = StackParser(str(tmp_path)).parse()

    assert result["languages"] == ["Kotlin"]
    assert "Quarkus" in result["frameworks"]


def test_composer_json_laravel(tmp_path: Path) -> None:
    (tmp_path / "composer.json").write_text(
        '{"require": {"laravel/framework": "^10.0"}}',
        encoding="utf-8",
    )

    result = StackParser(str(tmp_path)).parse()

    assert result["languages"] == ["PHP"]
    assert "laravel/framework" in result["dependencies"]
    assert "Laravel" in result["frameworks"]


def test_gemfile_rails(tmp_path: Path) -> None:
    (tmp_path / "Gemfile").write_text("gem 'rails', '~> 7.1'\n", encoding="utf-8")

    result = StackParser(str(tmp_path)).parse()

    assert result["languages"] == ["Ruby"]
    assert "rails" in result["dependencies"]
    assert "Rails" in result["frameworks"]


def test_malformed_composer_json_warning(tmp_path: Path) -> None:
    (tmp_path / "composer.json").write_text(
        '{"require": {"broken":',
        encoding="utf-8",
    )

    result = StackParser(str(tmp_path)).parse()

    assert result["dependencies"] == []
    assert len(result["manifest_warnings"]) == 1
    assert "composer.json" in result["manifest_warnings"][0]


def test_vue_in_package_json(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"dependencies": {"vue": "^3.4.0"}}',
        encoding="utf-8",
    )

    result = StackParser(str(tmp_path)).parse()

    assert "Vue" in result["frameworks"]


def test_fastapi_in_requirements(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("fastapi==0.109.0\n", encoding="utf-8")

    result = StackParser(str(tmp_path)).parse()

    assert "FastAPI" in result["frameworks"]


def test_gin_in_go_mod(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text(
        "module example.com/demo\n"
        "require github.com/gin-gonic/gin v1.9.0\n",
        encoding="utf-8",
    )

    result = StackParser(str(tmp_path)).parse()

    assert "Gin" in result["frameworks"]


def test_actix_web_in_cargo(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "demo"\nversion = "0.1.0"\n'
        '[dependencies]\nactix-web = "4"\n',
        encoding="utf-8",
    )

    result = StackParser(str(tmp_path)).parse()

    assert "Actix Web" in result["frameworks"]


def test_artisan_laravel_signature(tmp_path: Path) -> None:
    (tmp_path / "artisan").write_text("#!/usr/bin/env php\n", encoding="utf-8")

    result = StackParser(str(tmp_path)).parse()

    assert "Laravel" in result["frameworks"]


def test_sinatra_in_gemfile(tmp_path: Path) -> None:
    (tmp_path / "Gemfile").write_text("gem 'sinatra', '~> 3.0'\n", encoding="utf-8")

    result = StackParser(str(tmp_path)).parse()

    assert "Sinatra" in result["frameworks"]


def test_angular_json_signature(tmp_path: Path) -> None:
    (tmp_path / "angular.json").write_text("{}", encoding="utf-8")

    result = StackParser(str(tmp_path)).parse()

    assert "Angular" in result["frameworks"]


def test_no_false_positive_vue_router(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"dependencies": {"vue-router": "^4.0.0"}}',
        encoding="utf-8",
    )

    result = StackParser(str(tmp_path)).parse()

    assert "Vue" not in result["frameworks"]


def test_multi_ecosystem_framework_detection(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"dependencies": {"react": "^18.0.0", "express": "^4.18.0"}}',
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text("flask==3.0.0\n", encoding="utf-8")
    (tmp_path / "go.mod").write_text(
        "module example.com/demo\nrequire github.com/labstack/echo/v4 v4.11.0\n",
        encoding="utf-8",
    )
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "demo"\nversion = "0.1.0"\n'
        '[dependencies]\naxum = "0.7"\n',
        encoding="utf-8",
    )
    (tmp_path / "composer.json").write_text(
        '{"require": {"slim/slim": "^4.0"}}',
        encoding="utf-8",
    )
    (tmp_path / "Gemfile").write_text("gem 'sinatra'\n", encoding="utf-8")
    (tmp_path / "vite.config.ts").write_text("export default {}\n", encoding="utf-8")

    result = StackParser(str(tmp_path)).parse()

    assert result["frameworks"] == sorted(
        [
            "Axum",
            "Echo",
            "Express",
            "Flask",
            "React",
            "Sinatra",
            "Slim",
            "Vite",
        ]
    )
