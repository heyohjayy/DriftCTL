"""Terminal and Markdown renderers for classified, read-only scan results."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from driftctl.models import Finding, ResourceCategory, ScanResult, Severity
from driftctl.presentation import assess_impacts, explain_finding, readable_resource_type, remediation_plan


_SEVERITY_ORDER = (Severity.CRITICAL, Severity.SEVERE, Severity.MODERATE, Severity.MINOR)
_READ_ONLY_NOTICE = "DriftCTL reports drift only. It does not modify AWS or run Terraform."


def render_markdown(result: ScanResult) -> str:
    lines = ["# Infrastructure Drift Report", "", "## Scan Summary", ""]
    lines.extend(_markdown_summary(result))
    if result.diagnostics:
        lines.extend(["", "## Collection Diagnostics", ""])
        for diagnostic in result.diagnostics:
            address = f" `{diagnostic.resource_address}`" if diagnostic.resource_address else ""
            lines.append(f"- [{diagnostic.source}]{address}: {diagnostic.message}")
    if not result.findings:
        return "\n".join(lines + ["", "No drift detected.", "", _READ_ONLY_NOTICE, ""])

    grouped: dict[ResourceCategory, list[tuple[int, Finding]]] = defaultdict(list)
    for index, finding in enumerate(result.findings, start=1):
        grouped[finding.category].append((index, finding))
    for category in ResourceCategory:
        if not grouped[category]:
            continue
        lines.extend(["", f"## {category.value}", ""])
        for severity in _SEVERITY_ORDER:
            matches = [item for item in grouped[category] if item[1].severity is severity]
            if not matches:
                continue
            lines.extend([f"### {severity.value.title()}", ""])
            for index, finding in matches:
                lines.extend(_markdown_finding(index, finding))
    lines.extend([_READ_ONLY_NOTICE, ""])
    return "\n".join(lines)


def render_terminal(result: ScanResult, console: Console | None = None) -> None:
    output = console or Console()
    output.print(_summary_table(result))
    if result.diagnostics:
        output.print(Panel("\n".join(f"[{item.source}] {item.message}" for item in result.diagnostics), title="Collection Diagnostics", border_style="yellow"))
    if not result.findings:
        output.print(Panel(_READ_ONLY_NOTICE, title="No drift detected", border_style="green"))
        return
    for index, finding in enumerate(result.findings, start=1):
        output.print(_finding_panel(index, finding))


def _markdown_summary(result: ScanResult) -> list[str]:
    category_totals, severity_totals = _totals(result)
    return [
        "| Scan ID | Expected | Live | Findings | Active tag scope | Category totals | Severity totals |",
        "| --- | ---: | ---: | ---: | --- | --- | --- |",
        f"| `{result.scan_id}` | {result.expected_count} | {result.live_count} | {len(result.findings)} | {result.tag_scope} | {_format_totals(category_totals)} | {_format_totals(severity_totals)} |",
    ]


def _markdown_finding(index: int, finding: Finding) -> list[str]:
    impact = assess_impacts(finding)
    explanation = explain_finding(finding)
    plan = remediation_plan(finding)
    fields = _finding_fields(index, finding, impact, explanation, plan)
    lines = [f"#### {fields['Finding ID']}: {fields['Resource name']}", "", "| Field | Value |", "| --- | --- |"]
    for name in ("Status", "Resource type", "Category", "Severity", "Explanation", "Changed attributes", "Expected values", "Current/live values", "Security impact", "Cost impact", "Availability impact", "Requires approval"):
        lines.append(f"| {name} | {fields[name].replace(chr(10), '<br>')} |")
    lines.extend(["", "##### Remediation Plan", "", fields["Recommended next action"]])
    lines.extend(f"- {action}" for action in plan.actions)
    lines.extend(["", _READ_ONLY_NOTICE, ""])
    return lines


def _summary_table(result: ScanResult) -> Table:
    category_totals, severity_totals = _totals(result)
    table = Table(title="DriftCTL Scan Summary", show_header=True, header_style="bold cyan")
    for column in ("Scan ID", "Expected", "Live", "Findings", "Active tag scope", "Category totals", "Severity totals"):
        table.add_column(column)
    table.add_row(result.scan_id, str(result.expected_count), str(result.live_count), str(len(result.findings)), result.tag_scope, _format_totals(category_totals), _format_totals(severity_totals))
    return table


def _finding_panel(index: int, finding: Finding) -> Panel:
    impact = assess_impacts(finding)
    explanation = explain_finding(finding)
    plan = remediation_plan(finding)
    fields = _finding_fields(index, finding, impact, explanation, plan)
    details = Table.grid(padding=(0, 1))
    details.add_column(style="bold cyan", no_wrap=True)
    details.add_column(overflow="fold")
    for name in ("Finding ID", "Status", "Resource name", "Resource type", "Category", "Severity", "Explanation", "Changed attributes", "Expected values", "Current/live values", "Security impact", "Cost impact", "Availability impact", "Recommended next action", "Requires approval"):
        details.add_row(name, fields[name])
    actions = Text("\n".join(f"- {action}" for action in plan.actions))
    return Panel(Group(details, Text("Remediation Plan", style="bold cyan"), actions, Text(_READ_ONLY_NOTICE, style="italic")), title=f"DRIFT DETECTED | {fields['Finding ID']} | {fields['Severity'].upper()}", border_style=_severity_color(finding.severity), expand=False)


def _finding_fields(index: int, finding: Finding, impact: Any, explanation: Any, plan: Any) -> dict[str, str]:
    expected, live = _changed_values(finding)
    return {
        "Finding ID": f"DRIFT-{index:04d}", "Status": finding.drift_type.value,
        "Resource name": finding.identity.name, "Resource type": readable_resource_type(finding.identity.resource_type),
        "Category": finding.category.value, "Severity": finding.severity.value if finding.severity else "unclassified",
        "Explanation": f"{explanation.change}\n{explanation.consequence}",
        "Changed attributes": ", ".join(sorted(finding.changes)) or "Not applicable",
        "Expected values": expected, "Current/live values": live,
        "Security impact": impact.security.value, "Cost impact": impact.cost.value,
        "Availability impact": impact.availability.value, "Recommended next action": plan.recommended_action,
        "Requires approval": "YES",
    }


def _changed_values(finding: Finding) -> tuple[str, str]:
    if finding.changes:
        return (_render_value({key: value["expected"] for key, value in finding.changes.items()}), _render_value({key: value["live"] for key, value in finding.changes.items()}))
    return (_render_value(finding.expected.attributes) if finding.expected else "Not applicable", _render_value(finding.live.attributes) if finding.live else "Not applicable")


def _render_value(value: object) -> str:
    return json.dumps(value, default=str, sort_keys=True)


def _totals(result: ScanResult) -> tuple[Counter[str], Counter[str]]:
    return (Counter(finding.category.value for finding in result.findings), Counter((finding.severity.value if finding.severity else "unclassified") for finding in result.findings))


def _format_totals(totals: Counter[str]) -> str:
    return ", ".join(f"{name}: {count}" for name, count in sorted(totals.items())) or "None"


def _severity_color(severity: Severity | None) -> str:
    return {Severity.CRITICAL: "red", Severity.SEVERE: "bright_red", Severity.MODERATE: "yellow", Severity.MINOR: "blue"}.get(severity, "white")
