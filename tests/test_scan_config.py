from pathlib import Path

import pytest

from driftctl.cli import _resolve_options
from driftctl.scan_config import ScanConfigError, load_scan_config
from driftctl.scoping import parse_tag_scope


def _write_config(directory: Path, content: str) -> Path:
    path = directory / "driftctl.toml"
    path.write_text(content, encoding="utf-8")
    return path


def test_auto_discovers_driftctl_toml(tmp_path: Path) -> None:
    _write_config(tmp_path, """[scan]\nterraform_dir = \"terraform\"\naws_profile = \"readonly\"\nregion = \"eu-west-1\"\ntags = [\"Project=Test\"]\nreport = \"reports/report.md\"\naudit = \"audit/events.jsonl\"\n""")

    config = load_scan_config(None, tmp_path)

    assert config is not None
    assert config.terraform_dir == tmp_path / "terraform"
    assert config.tags == ("Project=Test",)


def test_explicit_config_path_overrides_auto_discovery(tmp_path: Path) -> None:
    _write_config(tmp_path, "[scan]\nregion = \"us-east-1\"\n")
    selected = tmp_path / "selected.toml"
    selected.write_text("[scan]\nregion = \"eu-west-1\"\n", encoding="utf-8")

    config = load_scan_config(selected, tmp_path)

    assert config is not None
    assert config.region == "eu-west-1"


def test_cli_values_take_precedence_over_config(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, """[scan]\nterraform_dir = \"configured\"\naws_profile = \"configured-profile\"\nregion = \"us-east-1\"\ntags = [\"Project=Configured\"]\nreport = \"configured-report.md\"\naudit = \"configured-audit.jsonl\"\n""")
    config = load_scan_config(config_path)

    resolved = _resolve_options(None, None, Path("cli-terraform"), "cli-profile", "eu-west-1", ["Project=Cli"], Path("cli-report.md"), Path("cli-audit.jsonl"), config)

    assert resolved[2:] == (Path("cli-terraform"), "cli-profile", "eu-west-1", ["Project=Cli"], Path("cli-report.md"), Path("cli-audit.jsonl"))


def test_malformed_or_secret_config_is_rejected(tmp_path: Path) -> None:
    malformed = _write_config(tmp_path, "[scan\n")
    with pytest.raises(ScanConfigError, match="Malformed TOML"):
        load_scan_config(malformed)
    secret = tmp_path / "secret.toml"
    secret.write_text("[scan]\naws_secret_access_key = \"never\"\n", encoding="utf-8")
    with pytest.raises(ScanConfigError, match="must not contain AWS secrets"):
        load_scan_config(secret)


def test_config_tags_propagate_and_are_validated(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, "[scan]\ntags = [\"Project=Test\", \"Environment=Sandbox\"]\n")
    config = load_scan_config(config_path)
    resolved = _resolve_options(None, None, None, None, None, [], None, None, config)

    assert parse_tag_scope(resolved[5]) == {"Project": "Test", "Environment": "Sandbox"}
    bad = tmp_path / "bad.toml"
    bad.write_text("[scan]\ntags = [\"invalid\"]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="KEY=VALUE"):
        parse_tag_scope(list(load_scan_config(bad).tags))


def test_explicit_offline_fixture_mode_ignores_discovered_config(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, """[scan]\nterraform_dir = \"configured\"\nregion = \"eu-west-1\"\ntags = [\"Project=Configured\"]\nreport = \"configured.md\"\naudit = \"configured.jsonl\"\n""")
    config = load_scan_config(config_path)
    expected, live = Path("expected.json"), Path("live.json")

    resolved = _resolve_options(expected, live, None, None, None, [], Path("report.md"), Path("audit.jsonl"), config)

    assert resolved == (expected, live, None, None, None, [], Path("report.md"), Path("audit.jsonl"))
