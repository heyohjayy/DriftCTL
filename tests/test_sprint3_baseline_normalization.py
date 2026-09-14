from driftctl.adapters.boto3_snapshots import adapt_boto3_inventory
from driftctl.adapters.terraform_state import adapt_terraform_state_with_diagnostics
from driftctl.detector import detect_drift
from driftctl.models import DriftType


def _terraform_state() -> dict:
    return {
        "values": {
            "root_module": {
                "resources": [
                    {
                        "address": "aws_network_acl.main",
                        "mode": "managed",
                        "type": "aws_network_acl",
                        "name": "main",
                        "values": {"id": "acl-1", "vpc_id": "vpc-1", "tags": {"Name": "main-acl"}},
                    },
                    {
                        "address": "aws_network_acl_rule.app_ingress",
                        "mode": "managed",
                        "type": "aws_network_acl_rule",
                        "name": "app_ingress",
                        "values": {"network_acl_id": "acl-1", "rule_no": 100, "egress": False, "protocol": "6", "rule_action": "allow", "cidr_block": "10.0.0.0/8", "ipv6_cidr_block": ""},
                    },
                    {
                        "address": "aws_route53_zone.private",
                        "mode": "managed",
                        "type": "aws_route53_zone",
                        "name": "private",
                        "values": {"id": "ZPRIVATE", "name": "internal.test.", "private_zone": False, "vpc": [{"vpc_id": "vpc-1"}], "tags": {"Project": "Test"}},
                    },
                    {
                        "address": "aws_route_table.public",
                        "mode": "managed",
                        "type": "aws_route_table",
                        "name": "public",
                        "values": {"id": "rtb-1", "vpc_id": "vpc-1", "tags": {"Name": "public"}, "route": [{"cidr_block": "0.0.0.0/0", "ipv6_cidr_block": "", "gateway_id": "igw-1"}]},
                    },
                ]
            }
        }
    }


def _live_inventory(*, user_rule_action: str = "allow") -> dict:
    return {
        "NetworkAcls": [
            {
                "NetworkAclId": "acl-1",
                "VpcId": "vpc-1",
                "Tags": [{"Key": "Name", "Value": "main-acl"}],
                "Associations": [],
                "Entries": [
                    {"RuleNumber": 100, "Egress": False, "Protocol": "6", "RuleAction": user_rule_action, "CidrBlock": "10.0.0.0/8", "Ipv6CidrBlock": None},
                    {"RuleNumber": 32767, "Egress": False, "Protocol": "-1", "RuleAction": "deny", "CidrBlock": "0.0.0.0/0"},
                    {"RuleNumber": 32767, "Egress": True, "Protocol": "-1", "RuleAction": "deny", "CidrBlock": "0.0.0.0/0"},
                ],
            }
        ],
        "HostedZones": [{"Id": "/hostedzone/ZPRIVATE", "Name": "internal.test.", "Config": {"PrivateZone": True}, "Tags": [{"Key": "Project", "Value": "Test"}]}],
        "RouteTables": [{"RouteTableId": "rtb-1", "VpcId": "vpc-1", "Tags": [{"Key": "Name", "Value": "public"}], "Associations": [], "Routes": [{"DestinationCidrBlock": "0.0.0.0/0", "DestinationIpv6CidrBlock": None, "GatewayId": "igw-1"}]}],
    }


def test_matching_acl_private_zone_and_public_igw_route_have_no_modified_drift() -> None:
    expected = adapt_terraform_state_with_diagnostics(_terraform_state()).snapshots
    live = adapt_boto3_inventory(_live_inventory())

    assert detect_drift(expected, live) == []


def test_user_defined_acl_rule_remains_detectable_after_default_rule_filtering() -> None:
    expected = adapt_terraform_state_with_diagnostics(_terraform_state()).snapshots
    live = adapt_boto3_inventory(_live_inventory(user_rule_action="deny"))

    findings = detect_drift(expected, live)

    assert len(findings) == 1
    assert findings[0].drift_type is DriftType.MODIFIED
    assert findings[0].identity.resource_type == "network_acl"
