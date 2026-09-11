from driftctl.adapters.boto3_snapshots import adapt_boto3_inventory
from driftctl.adapters.terraform_state import adapt_terraform_state_with_diagnostics
from driftctl.detector import detect_drift
from driftctl.models import CollectionDiagnostic, ScanResult, Severity
from driftctl.reporting import render_markdown
from driftctl.severity_rules import classify_finding, default_rules


def _terraform_state() -> dict:
    return {
        "values": {
            "root_module": {
                "resources": [
                    {
                        "address": "aws_security_group.web",
                        "mode": "managed",
                        "type": "aws_security_group",
                        "name": "web",
                        "values": {
                            "id": "sg-0123",
                            "group_name": "web",
                            "vpc_id": "vpc-0123",
                            "tags": {},
                        },
                    },
                    {
                        "address": "aws_vpc_security_group_ingress_rule.web_https",
                        "mode": "managed",
                        "type": "aws_vpc_security_group_ingress_rule",
                        "name": "web_https",
                        "values": {
                            "security_group_id": "sg-0123",
                            "ip_protocol": "tcp",
                            "from_port": 443,
                            "to_port": 443,
                            "cidr_ipv4": "10.0.0.0/8",
                        },
                    },
                    {
                        "address": "aws_vpc_security_group_egress_rule.web_https",
                        "mode": "managed",
                        "type": "aws_vpc_security_group_egress_rule",
                        "name": "web_https",
                        "values": {
                            "security_group_id": "sg-0123",
                            "ip_protocol": "tcp",
                            "from_port": 443,
                            "to_port": 443,
                            "cidr_ipv4": "198.51.100.0/24",
                        },
                    },
                ]
            }
        }
    }


def _live_security_group(include_public_ssh: bool = False) -> dict:
    ingress = [{
        "IpProtocol": "tcp",
        "FromPort": 443,
        "ToPort": 443,
        "IpRanges": [{"CidrIp": "10.0.0.0/8"}],
        "Ipv6Ranges": [],
    }]
    if include_public_ssh:
        ingress.append({
            "IpProtocol": "tcp",
            "FromPort": 22,
            "ToPort": 22,
            "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
            "Ipv6Ranges": [],
        })
    return {
        "SecurityGroups": [{
            "GroupId": "sg-0123",
            "GroupName": "web",
            "VpcId": "vpc-0123",
            "IpPermissions": ingress,
            "IpPermissionsEgress": [{
                "IpProtocol": "tcp",
                "FromPort": 443,
                "ToPort": 443,
                "IpRanges": [{"CidrIp": "198.51.100.0/24"}],
                "Ipv6Ranges": [],
            }],
            "Tags": [],
        }]
    }


def test_standalone_security_group_rules_match_boto3_permissions_without_drift() -> None:
    expected = adapt_terraform_state_with_diagnostics(_terraform_state())
    live = adapt_boto3_inventory(_live_security_group())

    assert expected.diagnostics == ()
    assert expected.snapshots[0].attributes["ingress"][0]["cidr_blocks"] == ["10.0.0.0/8"]
    assert expected.snapshots[0].attributes["egress"][0]["cidr_blocks"] == ["198.51.100.0/24"]
    assert detect_drift(expected.snapshots, live) == []


def test_added_public_ssh_on_standalone_rule_security_group_is_critical() -> None:
    expected = adapt_terraform_state_with_diagnostics(_terraform_state())
    findings = detect_drift(expected.snapshots, adapt_boto3_inventory(_live_security_group(include_public_ssh=True)))

    assert len(findings) == 1
    assert findings[0].drift_type.value == "modified"
    assert "ingress" in findings[0].changes
    classify_finding(findings[0], default_rules())
    assert findings[0].severity is Severity.CRITICAL


def test_unsupported_managed_resource_is_reported_as_a_collection_diagnostic() -> None:
    adaptation = adapt_terraform_state_with_diagnostics({
        "values": {
            "root_module": {
                "resources": [{
                    "address": "aws_db_instance.legacy",
                    "mode": "managed",
                    "type": "aws_db_instance",
                    "name": "legacy",
                    "values": {"id": "database-1"},
                }]
            }
        }
    })

    assert adaptation.snapshots == []
    assert adaptation.diagnostics == (
        CollectionDiagnostic(
            source="terraform_state",
            resource_address="aws_db_instance.legacy",
            message="Skipped unsupported Terraform resource type: aws_db_instance.",
        ),
    )
    report = render_markdown(ScanResult("scan-1", "2026-09-11T00:00:00+00:00", 0, 0, (), adaptation.diagnostics))
    assert "## Collection Diagnostics" in report
    assert "Skipped unsupported Terraform resource type: aws_db_instance." in report
