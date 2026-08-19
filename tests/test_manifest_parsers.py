from pathlib import Path

from rebrief.parsers.manifests.cargo import parse as parse_cargo
from rebrief.parsers.manifests.composer import parse as parse_composer
from rebrief.parsers.manifests.gemfile import parse as parse_gemfile
from rebrief.parsers.manifests.go import parse as parse_go
from rebrief.parsers.manifests.gradle import parse as parse_gradle
from rebrief.parsers.manifests.package_json import parse as parse_package_json
from rebrief.parsers.manifests.pyproject import parse as parse_pyproject
from rebrief.parsers.manifests.pom import parse as parse_pom

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "manifests"


def test_go_valid_fixture() -> None:
    result = parse_go(FIXTURES_DIR / "go" / "valid.go.mod")

    assert result.get("error") is None
    assert result["metadata"]["module"] == "example.com/demo"
    assert result["metadata"]["go_version"] == "1.22"
    assert "github.com/gin-gonic/gin" in result["dependencies"]
    assert "github.com/stretchr/testify" not in result["dependencies"]
    packages = result.get("packages", [])
    gin = next(pkg for pkg in packages if pkg["name"] == "github.com/gin-gonic/gin")
    assert gin["version"] == "1.9.0"
    assert gin["ecosystem"] == "Go"
    assert gin["exact"] is True


def test_cargo_valid_fixture() -> None:
    result = parse_cargo(FIXTURES_DIR / "cargo" / "valid.Cargo.toml")

    assert result.get("error") is None
    assert result["metadata"]["name"] == "demo"
    assert result["metadata"]["version"] == "0.1.0"
    assert "serde" in result["dependencies"]
    assert "axum" in result["dependencies"]
    assert "tokio" in result["dependencies"]
    serde = next(pkg for pkg in result.get("packages", []) if pkg["name"] == "serde")
    assert serde["version"] == "1.0"
    assert serde["ecosystem"] == "crates.io"
    assert serde["exact"] is False


def test_cargo_malformed_fixture() -> None:
    result = parse_cargo(FIXTURES_DIR / "cargo" / "malformed.Cargo.toml")

    assert result["dependencies"] == []
    assert result.get("error") is not None


def test_pom_valid_fixture() -> None:
    result = parse_pom(FIXTURES_DIR / "maven" / "valid.pom.xml")

    assert result.get("error") is None
    assert "spring-boot-starter-web" in result["dependencies"]


def test_pom_malformed_fixture() -> None:
    result = parse_pom(FIXTURES_DIR / "maven" / "malformed.pom.xml")

    assert result["dependencies"] == []
    assert result.get("error") is not None


def test_gradle_valid_fixture() -> None:
    result = parse_gradle(FIXTURES_DIR / "gradle" / "valid.build.gradle.kts")

    assert result.get("error") is None
    assert "io.quarkus:quarkus-resteasy-reactive:3.6.0" in result["dependencies"]
    assert "io.quarkus:quarkus-arc:3.6.0" in result["dependencies"]


def test_composer_valid_fixture() -> None:
    result = parse_composer(FIXTURES_DIR / "composer" / "valid.composer.json")

    assert result.get("error") is None
    assert "laravel/framework" in result["dependencies"]
    assert "monolog/monolog" in result["dependencies"]
    assert "phpunit/phpunit" in result["dependencies"]
    laravel = next(
        pkg for pkg in result.get("packages", []) if pkg["name"] == "laravel/framework"
    )
    assert laravel["version"] == "10.0"
    assert laravel["ecosystem"] == "Packagist"
    assert laravel["exact"] is False


def test_composer_malformed_fixture() -> None:
    result = parse_composer(FIXTURES_DIR / "composer" / "malformed.composer.json")

    assert result["dependencies"] == []
    assert result.get("error") is not None


def test_gemfile_valid_fixture() -> None:
    result = parse_gemfile(FIXTURES_DIR / "gemfile" / "valid.Gemfile")

    assert result.get("error") is None
    assert "rails" in result["dependencies"]
    assert "puma" in result["dependencies"]
    assert "sqlite3" in result["dependencies"]


def test_gemfile_malformed_fixture_still_parses_valid_gems() -> None:
    result = parse_gemfile(FIXTURES_DIR / "gemfile" / "malformed.Gemfile")

    assert result.get("error") is None
    assert "rails" in result["dependencies"]


def test_package_json_extracts_versions(tmp_path: Path) -> None:
    path = tmp_path / "package.json"
    path.write_text(
        """{
  "dependencies": {
    "react": "^18.0.0",
    "lodash": "4.17.21"
  }
}""",
        encoding="utf-8",
    )
    result = parse_package_json(path)

    assert "react" in result["dependencies"]
    assert "lodash" in result["dependencies"]
    react = next(pkg for pkg in result.get("packages", []) if pkg["name"] == "react")
    lodash = next(pkg for pkg in result.get("packages", []) if pkg["name"] == "lodash")
    assert react["version"] == "18.0.0"
    assert react["exact"] is False
    assert lodash["version"] == "4.17.21"
    assert lodash["exact"] is True


def test_pyproject_extracts_versions(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text(
        """[project]
dependencies = [
    "django==4.2.0",
    "click>=8.1",
]
""",
        encoding="utf-8",
    )
    result = parse_pyproject(path)

    assert "django==4.2.0" in result["dependencies"]
    django = next(pkg for pkg in result.get("packages", []) if pkg["name"] == "django")
    click = next(pkg for pkg in result.get("packages", []) if pkg["name"] == "click")
    assert django["version"] == "4.2.0"
    assert django["exact"] is True
    assert click["version"] == "8.1"
    assert click["exact"] is False
