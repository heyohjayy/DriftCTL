"""Typer command-line entry point for read-only drift scans."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import typer

from driftctl.adapters.boto3_snapshots import adapt_boto3_inventory
from driftctl.adapters.terraform_state import adapt_terraform_state
from driftctl.audit import write_audit_log
from driftctl.collectors.aws import AwsCollectionError, collect_live_inventory
from driftctl.detector import detect_drift
from driftctl.loaders.terraform_cli import TerraformStateLoadError, load_terraform_state
from driftctl.models import ScanResult
from driftctl.reporting import render_markdown
from driftctl.severity_rules import classify_finding, default_rules


app = typer.Typer(help="Read-only Terraform-to-AWS inventory drift control.", no_args_is_help=True)


@app.callback()
def main() -> None:
    """Inspect drift and produce evidence; never modify infrastructure."""


@app.command()
def scan(
    expected: Path | None = typer.Option(None, "--expected", exists=True, readable=True, help="Terraform show -json-style expected inventory fixture."),
    live: Path | None = typer.Option(None, "--live", exists=True, readable=True, help="Boto3 response-style live inventory fixture."),
    terraform_dir: Path | None = typer.Option(None, "--terraform-dir", exists=True, file_okay=False, readable=True, help="Initialized Terraform directory to inspect with terraform show -json."),
    profile: str | None = typer.Option(None, "--profile", help="AWS shared-config profile for live collection."),
    region: str | None = typer.Option(None, "--region", help="AWS region for live collection."),
    role_arn: str | None = typer.Option(None, "--role-arn", help="Optional role to assume before live collection."),
    report: Path = typer.Option(..., "--report", help="Markdown report destination."),
    audit: Path = typer.Option(..., "--audit", help="Append-only JSONL audit destination."),
) -> None:
    """Compare inventories and write findings without modifying infrastructure."""
    try:
        _validate_sources(expected, live, terraform_dir, profile, region, role_arn)
        expected_payload = _load_json(expected) if expected else load_terraform_state(terraform_dir)
        live_payload = _load_json(live) if live else collect_live_inventory(profile, region, role_arn)
        expected_snapshots = adapt_terraform_state(expected_payload)
        live_snapshots = adapt_boto3_inventory(live_payload)
        findings = detect_drift(expected_snapshots, live_snapshots)
        rules = default_rules()
        for finding in findings:
            classify_finding(finding, rules)
        result = ScanResult(str(uuid4()), datetime.now(UTC).isoformat(), len(expected_snapshots), len(live_snapshots), tuple(findings))
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(render_markdown(result), encoding="utf-8")
        event_count = write_audit_log(audit, result)
    except (AwsCollectionError, OSError, TerraformStateLoadError, ValueError, KeyError, json.JSONDecodeError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(f"Scan complete: {len(findings)} finding(s); report: {report}; audit events appended: {event_count}")


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def _validate_sources(
    expected: Path | None,
    live: Path | None,
    terraform_dir: Path | None,
    profile: str | None,
    region: str | None,
    role_arn: str | None,
) -> None:
    if (expected is None) == (terraform_dir is None):
        raise ValueError("Provide exactly one expected source: --expected or --terraform-dir.")
    if live is not None and any((profile, region, role_arn)):
        raise ValueError("--profile, --region, and --role-arn are only valid when collecting live AWS inventory.")
    if live is None and not region:
        raise ValueError("--region is required when --live is omitted for real AWS collection.")


if __name__ == "__main__":
    app()
