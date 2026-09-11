"""Read Terraform state through the Terraform CLI without modifying it."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


class TerraformStateLoadError(RuntimeError):
    """Terraform could not provide a valid JSON state representation."""


def load_terraform_state(terraform_dir: Path, terraform_binary: str = "terraform") -> dict[str, Any]:
    """Run `terraform show -json` against an initialized working directory."""
    command = [terraform_binary, f"-chdir={terraform_dir}", "show", "-json"]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as error:
        raise TerraformStateLoadError(f"Unable to start Terraform: {error}") from error
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "Terraform returned no error output."
        raise TerraformStateLoadError(f"terraform show -json failed: {detail}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise TerraformStateLoadError("terraform show -json returned invalid JSON.") from error
