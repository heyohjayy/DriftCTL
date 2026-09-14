"""Typer command-line entry point for read-only drift scans."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import typer

from driftctl.adapters.boto3_snapshots import adapt_boto3_inventory
from driftctl.adapters.terraform_state import adapt_terraform_state_with_diagnostics
from driftctl.audit import write_audit_log
from driftctl.collectors.aws import AwsCollectionError, collect_live_inventory
from driftctl.detector import detect_drift
from driftctl.loaders.terraform_cli import TerraformStateLoadError, load_terraform_state
from driftctl.models import CollectionDiagnostic, ScanResult
from driftctl.reporting import render_markdown, render_terminal
from driftctl.scan_config import ScanConfig, ScanConfigError, load_scan_config
from driftctl.scoping import filter_snapshots_by_tag_scope, format_tag_scope, parse_tag_scope
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
    tag: list[str] = typer.Option([], "--tag", help="Repeatable environment scope in KEY=VALUE form."),
    report: Path | None = typer.Option(None, "--report", help="Markdown report destination."),
    audit: Path | None = typer.Option(None, "--audit", help="Append-only JSONL audit destination."),
    config: Path | None = typer.Option(None, "--config", help="Optional driftctl.toml scan configuration."),
) -> None:
    """Compare inventories and write findings without modifying infrastructure."""
    try:
        configured = load_scan_config(config)
        expected, live, terraform_dir, profile, region, tag, report, audit = _resolve_options(
            expected, live, terraform_dir, profile, region, tag, report, audit, configured
        )
        tag_scope = parse_tag_scope(tag)
        _validate_sources(expected, live, terraform_dir, profile, region, role_arn)
        _validate_paths(expected, live, terraform_dir, report, audit)
        expected_payload = _load_json(expected) if expected else load_terraform_state(terraform_dir)
        live_payload = _load_json(live) if live else collect_live_inventory(profile, region, role_arn, tag_scope)
        expected_adaptation = adapt_terraform_state_with_diagnostics(expected_payload)
        expected_snapshots = filter_snapshots_by_tag_scope(expected_adaptation.snapshots, tag_scope)
        live_snapshots = filter_snapshots_by_tag_scope(adapt_boto3_inventory(live_payload), tag_scope)
        findings = detect_drift(expected_snapshots, live_snapshots)
        rules = default_rules()
        for finding in findings:
            classify_finding(finding, rules)
        result = ScanResult(
            str(uuid4()),
            datetime.now(UTC).isoformat(),
            len(expected_snapshots),
            len(live_snapshots),
            tuple(findings),
            expected_adaptation.diagnostics + _live_collection_diagnostics(live_payload) + _scope_diagnostics(tag_scope),
            format_tag_scope(tag_scope) if tag_scope else "None",
        )
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(render_markdown(result), encoding="utf-8")
        event_count = write_audit_log(audit, result)
    except (AwsCollectionError, OSError, ScanConfigError, TerraformStateLoadError, ValueError, KeyError, json.JSONDecodeError) as error:
        raise typer.BadParameter(str(error)) from error
    render_terminal(result)
    typer.echo(f"Scan complete: {len(findings)} finding(s); report: {report}; audit events appended: {event_count}")


def _resolve_options(
    expected: Path | None,
    live: Path | None,
    terraform_dir: Path | None,
    profile: str | None,
    region: str | None,
    tags: list[str],
    report: Path | None,
    audit: Path | None,
    configured: ScanConfig | None,
) -> tuple[Path | None, Path | None, Path | None, str | None, str | None, list[str], Path | None, Path | None]:
    """Apply TOML defaults only where an explicit CLI input is absent."""
    if configured is None or expected is not None and live is not None:
        return expected, live, terraform_dir, profile, region, tags, report, audit
    return (
        expected,
        live,
        terraform_dir or (None if expected is not None else configured.terraform_dir),
        profile if live is not None else profile or configured.aws_profile,
        region if live is not None else region or configured.region,
        tags or list(configured.tags),
        report or configured.report,
        audit or configured.audit,
    )


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


def _validate_paths(
    expected: Path | None,
    live: Path | None,
    terraform_dir: Path | None,
    report: Path | None,
    audit: Path | None,
) -> None:
    if report is None or audit is None:
        raise ValueError("Provide --report and --audit, or configure both in [scan].")
    if expected is not None and not expected.is_file():
        raise ValueError(f"Expected inventory file does not exist: {expected}")
    if live is not None and not live.is_file():
        raise ValueError(f"Live inventory file does not exist: {live}")
    if terraform_dir is not None and not terraform_dir.is_dir():
        raise ValueError(f"Terraform directory does not exist: {terraform_dir}")


def _scope_diagnostics(tag_scope: dict[str, str]) -> tuple[CollectionDiagnostic, ...]:
    if not tag_scope:
        return ()
    return (CollectionDiagnostic("tag_scope", f"Active tag scope: {format_tag_scope(tag_scope)}."),)


def _live_collection_diagnostics(payload: dict) -> tuple[CollectionDiagnostic, ...]:
    return tuple(
        CollectionDiagnostic(item.get("source", "aws_collection"), item.get("message", "Collection limitation."))
        for item in payload.get("CollectionDiagnostics", [])
    )


if __name__ == "__main__":
    app()
