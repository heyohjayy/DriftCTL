from pathlib import Path

from typer.testing import CliRunner

from driftctl.cli import app


runner = CliRunner()


def test_init_creates_a_non_secret_configuration(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["init", "--directory", str(tmp_path), "--profile", "scanner", "--region", "eu-west-1", "--tag", "Project=Test"],
    )

    assert result.exit_code == 0
    assert (tmp_path / "driftctl.toml").read_text(encoding="utf-8") == (
        '[scan]\n'
        'terraform_dir = "."\n'
        'aws_profile = "scanner"\n'
        'region = "eu-west-1"\n'
        'tags = ["Project=Test"]\n'
        'report = "driftctl-output/live-report.md"\n'
        'audit = "driftctl-output/events.jsonl"\n'
    )


def test_init_prompts_for_values_and_does_not_overwrite(tmp_path: Path) -> None:
    created = runner.invoke(app, ["init", "--directory", str(tmp_path)], input="driftctl-readonly\neu-west-1\n\n")
    existing = runner.invoke(app, ["init", "--directory", str(tmp_path)])

    assert created.exit_code == 0
    assert 'tags = []' in (tmp_path / "driftctl.toml").read_text(encoding="utf-8")
    assert existing.exit_code == 1
    assert "Use --force" in existing.output
