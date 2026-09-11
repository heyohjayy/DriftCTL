import subprocess
from pathlib import Path

import pytest

from driftctl.loaders.terraform_cli import TerraformStateLoadError, load_terraform_state


def test_loads_terraform_show_json_without_state_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        recorded["command"] = command
        recorded["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, '{"values": {"root_module": {}}}', "")

    monkeypatch.setattr("driftctl.loaders.terraform_cli.subprocess.run", fake_run)

    payload = load_terraform_state(Path("infra/terraform"))

    assert payload == {"values": {"root_module": {}}}
    assert recorded["command"] == ["terraform", f"-chdir={Path('infra/terraform')}", "show", "-json"]
    assert recorded["kwargs"] == {"capture_output": True, "text": True, "check": False}


def test_loader_raises_clear_error_on_terraform_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "driftctl.loaders.terraform_cli.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 1, "", "No state file was found."),
    )
    with pytest.raises(TerraformStateLoadError, match="No state file was found"):
        load_terraform_state(Path("infra/terraform"))
