from driftctl.adapters.boto3_snapshots import adapt_boto3_inventory
from driftctl.adapters.terraform_state import adapt_terraform_state_with_diagnostics
from driftctl.detector import detect_drift
from driftctl.models import DriftType, Finding, ResourceCategory, ResourceIdentity, ResourceSnapshot, Severity
from driftctl.severity_rules import classify_finding, default_rules
from driftctl.scoping import filter_snapshots_by_tag_scope


def test_terraform_network_children_aggregate_to_parent_snapshots() -> None:
    state = {"values": {"root_module": {"resources": [
        {"address": "aws_route_table.main", "mode": "managed", "type": "aws_route_table", "name": "main", "values": {"id": "rtb-1", "vpc_id": "vpc-1", "tags": {"Name": "main", "Project": "Test"}}},
        {"address": "aws_route.public", "mode": "managed", "type": "aws_route", "name": "public", "values": {"route_table_id": "rtb-1", "destination_cidr_block": "0.0.0.0/0", "gateway_id": "igw-1"}},
        {"address": "aws_route_table_association.main", "mode": "managed", "type": "aws_route_table_association", "name": "main", "values": {"route_table_id": "rtb-1", "subnet_id": "subnet-1"}},
        {"address": "aws_network_acl.main", "mode": "managed", "type": "aws_network_acl", "name": "main", "values": {"id": "acl-1", "vpc_id": "vpc-1", "tags": {"Name": "main-acl", "Project": "Test"}}},
        {"address": "aws_network_acl_rule.public", "mode": "managed", "type": "aws_network_acl_rule", "name": "public", "values": {"network_acl_id": "acl-1", "egress": False, "rule_number": 100, "protocol": "-1", "rule_action": "allow", "cidr_block": "0.0.0.0/0"}},
        {"address": "aws_network_acl_association.main", "mode": "managed", "type": "aws_network_acl_association", "name": "main", "values": {"network_acl_id": "acl-1", "subnet_id": "subnet-1"}},
    ]}}}
    snapshots = adapt_terraform_state_with_diagnostics(state).snapshots
    route_table = next(item for item in snapshots if item.identity.resource_type == "route_table")
    acl = next(item for item in snapshots if item.identity.resource_type == "network_acl")
    assert route_table.attributes["routes"][0]["target"] == "igw-1"
    assert route_table.attributes["associations"] == [{"subnet_id": "subnet-1"}]
    assert acl.attributes["entries"][0]["cidr_block"] == "0.0.0.0/0"


def test_boto3_network_identity_and_dns_snapshots_are_scope_filterable() -> None:
    payload = {
        "Vpcs": [{"VpcId": "vpc-1", "CidrBlock": "10.0.0.0/16", "Tags": [{"Key": "Project", "Value": "Test"}]}],
        "RouteTables": [{"RouteTableId": "rtb-1", "VpcId": "vpc-1", "Routes": [], "Associations": [], "Tags": [{"Key": "Project", "Value": "Test"}]}],
        "NetworkAcls": [{"NetworkAclId": "acl-1", "VpcId": "vpc-1", "Entries": [], "Associations": [], "Tags": [{"Key": "Project", "Value": "Test"}]}],
        "IamRoles": [{"RoleName": "role", "AssumeRolePolicyDocument": {}, "ManagedPolicyArns": [], "InlinePolicies": [], "Tags": [{"Key": "Project", "Value": "Test"}]}, {"RoleName": "outside-role", "AssumeRolePolicyDocument": {}, "Tags": [{"Key": "Project", "Value": "Other"}]}],
        "InstanceProfiles": [{"InstanceProfileName": "profile", "Roles": [{"RoleName": "role"}], "Tags": [{"Key": "Project", "Value": "Test"}]}],
        "HostedZones": [{"Id": "/hostedzone/Z1", "Name": "example.test.", "Config": {"PrivateZone": False}, "Tags": [{"Key": "Project", "Value": "Test"}]}, {"Id": "/hostedzone/Z2", "Name": "outside.test.", "Config": {"PrivateZone": False}, "Tags": [{"Key": "Project", "Value": "Other"}]}],
        "RecordSets": {"/hostedzone/Z1": [{"Name": "api.example.test.", "Type": "A", "TTL": 60, "ResourceRecords": [{"Value": "192.0.2.10"}]}], "/hostedzone/Z2": [{"Name": "api.outside.test.", "Type": "A", "ResourceRecords": [{"Value": "192.0.2.11"}]}]},
    }
    names = {snapshot.identity.key for snapshot in filter_snapshots_by_tag_scope(adapt_boto3_inventory(payload), {"Project": "Test"})}
    assert "aws:route53_record:example.test|api.example.test|A" in names
    assert "aws:iam_role:role" in names
    assert "aws:route53_record:outside.test|api.outside.test|A" not in names
    assert "aws:iam_role:outside-role" not in names


def test_clean_vpc_and_dns_state_matches_live_inventory() -> None:
    state = {"values": {"root_module": {"resources": [
        {"address": "aws_vpc.main", "mode": "managed", "type": "aws_vpc", "name": "main", "values": {"id": "vpc-1", "cidr_block": "10.0.0.0/16", "tags": {"Name": "main", "Project": "Test"}}},
        {"address": "aws_route53_zone.main", "mode": "managed", "type": "aws_route53_zone", "name": "main", "values": {"id": "Z1", "name": "example.test.", "private_zone": False, "tags": {"Project": "Test"}}},
        {"address": "aws_route53_record.api", "mode": "managed", "type": "aws_route53_record", "name": "api", "values": {"zone_id": "Z1", "name": "api.example.test.", "type": "A", "ttl": 60, "records": ["192.0.2.10"]}},
    ]}}}
    live = {"Vpcs": [{"VpcId": "vpc-1", "CidrBlock": "10.0.0.0/16", "Tags": [{"Key": "Name", "Value": "main"}, {"Key": "Project", "Value": "Test"}]}], "HostedZones": [{"Id": "Z1", "Name": "example.test.", "Config": {"PrivateZone": False}, "Tags": [{"Key": "Project", "Value": "Test"}]}], "RecordSets": {"Z1": [{"Name": "api.example.test.", "Type": "A", "TTL": 60, "ResourceRecords": [{"Value": "192.0.2.10"}]}]}}
    assert detect_drift(adapt_terraform_state_with_diagnostics(state).snapshots, adapt_boto3_inventory(live)) == []
    live["RecordSets"]["Z1"][0]["ResourceRecords"] = [{"Value": "192.0.2.11"}]
    assert [item.drift_type for item in detect_drift(adapt_terraform_state_with_diagnostics(state).snapshots, adapt_boto3_inventory(live))] == [DriftType.MODIFIED]


def test_implicit_local_route_does_not_modify_matching_route_table() -> None:
    state = {"values": {"root_module": {"resources": [
        {"address": "aws_route_table.main", "mode": "managed", "type": "aws_route_table", "name": "main", "values": {"id": "rtb-1", "vpc_id": "vpc-1", "tags": {"Name": "main"}, "route": [{"destination_cidr_block": "0.0.0.0/0", "gateway_id": "igw-1"}]}},
    ]}}}
    live = {"RouteTables": [{"RouteTableId": "rtb-1", "VpcId": "vpc-1", "Tags": [{"Key": "Name", "Value": "main"}], "Associations": [], "Routes": [
        {"DestinationCidrBlock": "10.0.0.0/16", "GatewayId": "local", "Origin": "CreateRouteTable"},
        {"DestinationCidrBlock": "0.0.0.0/0", "GatewayId": "igw-1", "Origin": "CreateRoute"},
    ]}]}
    assert detect_drift(adapt_terraform_state_with_diagnostics(state).snapshots, adapt_boto3_inventory(live)) == []


def test_tag_scope_excludes_new_network_identity_and_dns_resources() -> None:
    payload = {
        "Vpcs": [{"VpcId": "vpc-in", "CidrBlock": "10.0.0.0/16", "Tags": [{"Key": "Project", "Value": "Test"}]}, {"VpcId": "vpc-out", "CidrBlock": "10.1.0.0/16", "Tags": [{"Key": "Project", "Value": "Other"}]}],
        "IamRoles": [{"RoleName": "in", "AssumeRolePolicyDocument": {}, "Tags": [{"Key": "Project", "Value": "Test"}]}, {"RoleName": "out", "AssumeRolePolicyDocument": {}, "Tags": [{"Key": "Project", "Value": "Other"}]}],
        "HostedZones": [{"Id": "ZIN", "Name": "in.test.", "Config": {}, "Tags": [{"Key": "Project", "Value": "Test"}]}, {"Id": "ZOUT", "Name": "out.test.", "Config": {}, "Tags": [{"Key": "Project", "Value": "Other"}]}],
        "RecordSets": {"ZIN": [{"Name": "api.in.test.", "Type": "A", "ResourceRecords": [{"Value": "192.0.2.10"}]}], "ZOUT": [{"Name": "api.out.test.", "Type": "A", "ResourceRecords": [{"Value": "192.0.2.11"}]}]},
    }
    scoped = filter_snapshots_by_tag_scope(adapt_boto3_inventory(payload), {"Project": "Test"})
    assert {item.identity.name for item in scoped} == {"vpc-in", "in", "in.test", "in.test|api.in.test|A"}


def test_sprint3_severity_rules_cover_each_service_family() -> None:
    cases = [
        Finding(DriftType.MODIFIED, ResourceIdentity("aws", "route_table", "rt"), ResourceCategory.NETWORKING, live=ResourceSnapshot(ResourceIdentity("aws", "route_table", "rt"), ResourceCategory.NETWORKING, {"routes": [{"destination_ipv4": "0.0.0.0/0", "target_type": "internet_gateway"}]}), changes={"routes": {}}),
        Finding(DriftType.MODIFIED, ResourceIdentity("aws", "network_acl", "acl"), ResourceCategory.NETWORKING, live=ResourceSnapshot(ResourceIdentity("aws", "network_acl", "acl"), ResourceCategory.NETWORKING, {"entries": [{"egress": False, "action": "allow", "cidr_block": "0.0.0.0/0", "protocol": "-1"}]}), changes={"entries": {}}),
        Finding(DriftType.MODIFIED, ResourceIdentity("aws", "iam_role", "admin"), ResourceCategory.IAM, live=ResourceSnapshot(ResourceIdentity("aws", "iam_role", "admin"), ResourceCategory.IAM, {"managed_policy_arns": ["arn:aws:iam::aws:policy/AdministratorAccess"], "trust_policy": {}}), changes={"managed_policy_arns": {}}),
        Finding(DriftType.MODIFIED, ResourceIdentity("aws", "route53_record", "z|a|A"), ResourceCategory.OTHER),
    ]
    for finding in cases: classify_finding(finding, default_rules())
    assert [item.severity for item in cases] == [Severity.SEVERE, Severity.SEVERE, Severity.CRITICAL, Severity.MODERATE]


def test_in_scope_unmanaged_route53_record_is_detected() -> None:
    live = ResourceSnapshot(ResourceIdentity("aws", "route53_record", "zone|api.zone|A"), ResourceCategory.OTHER, {"tags": {"Project": "Test"}})
    findings = detect_drift([], [live])
    assert [(item.drift_type, item.identity.resource_type) for item in findings] == [(DriftType.UNMANAGED, "route53_record")]


def _private_zone_state(*, include_apex_soa: bool = False) -> dict:
    resources = [
        {
            "address": "aws_route53_zone.private",
            "mode": "managed",
            "type": "aws_route53_zone",
            "name": "private",
            "values": {
                "id": "ZPRIVATE",
                "name": "internal.test.",
                "private_zone": True,
                "tags": {"Project": "Test"},
            },
        },
        {
            "address": "aws_route53_record.app",
            "mode": "managed",
            "type": "aws_route53_record",
            "name": "app",
            "values": {
                "zone_id": "ZPRIVATE",
                "name": "app.internal.test.",
                "type": "A",
                "ttl": 60,
                "records": ["10.0.1.10"],
            },
        },
    ]
    if include_apex_soa:
        resources.append(
            {
                "address": "aws_route53_record.apex_soa",
                "mode": "managed",
                "type": "aws_route53_record",
                "name": "apex_soa",
                "values": {
                    "zone_id": "ZPRIVATE",
                    "name": "internal.test.",
                    "type": "SOA",
                    "ttl": 900,
                    "records": [
                        "ns-1.awsdns.test. hostmaster.awsdns.test. "
                        "1 7200 900 1209600 86400"
                    ],
                },
            }
        )
    return {"values": {"root_module": {"resources": resources}}}


def _private_zone_live() -> dict:
    return {
        "HostedZones": [
            {
                "Id": "/hostedzone/ZPRIVATE",
                "Name": "internal.test.",
                "Config": {"PrivateZone": True},
                "Tags": [{"Key": "Project", "Value": "Test"}],
            }
        ],
        "RecordSets": {
            "/hostedzone/ZPRIVATE": [
                {
                    "Name": "internal.test.",
                    "Type": "SOA",
                    "TTL": 900,
                    "ResourceRecords": [
                        {
                            "Value": "ns-1.awsdns.test. hostmaster.awsdns.test. "
                            "1 7200 900 1209600 86400"
                        }
                    ],
                },
                {
                    "Name": "internal.test.",
                    "Type": "NS",
                    "TTL": 172800,
                    "ResourceRecords": [
                        {"Value": "ns-1.awsdns.test."},
                        {"Value": "ns-2.awsdns.test."},
                    ],
                },
                {
                    "Name": "app.internal.test.",
                    "Type": "A",
                    "TTL": 60,
                    "ResourceRecords": [{"Value": "10.0.1.10"}],
                },
            ]
        },
    }


def test_route53_default_apex_records_do_not_create_unmanaged_drift() -> None:
    expected = adapt_terraform_state_with_diagnostics(_private_zone_state()).snapshots
    live = adapt_boto3_inventory(_private_zone_live())

    assert detect_drift(expected, live) == []


def test_route53_managed_a_record_change_remains_modified_drift() -> None:
    payload = _private_zone_live()
    payload["RecordSets"]["/hostedzone/ZPRIVATE"][2]["ResourceRecords"] = [
        {"Value": "10.0.1.99"}
    ]
    expected = adapt_terraform_state_with_diagnostics(_private_zone_state()).snapshots

    findings = detect_drift(expected, adapt_boto3_inventory(payload))

    assert len(findings) == 1
    assert findings[0].drift_type is DriftType.MODIFIED
    assert findings[0].identity.name == "internal.test|app.internal.test|A"


def test_explicit_apex_system_record_uses_normal_comparison() -> None:
    payload = _private_zone_live()
    expected = adapt_terraform_state_with_diagnostics(
        _private_zone_state(include_apex_soa=True)
    ).snapshots

    assert detect_drift(expected, adapt_boto3_inventory(payload)) == []

    payload["RecordSets"]["/hostedzone/ZPRIVATE"][0]["ResourceRecords"] = [
        {
            "Value": "ns-1.awsdns.test. hostmaster.awsdns.test. "
            "2 7200 900 1209600 86400"
        }
    ]
    findings = detect_drift(expected, adapt_boto3_inventory(payload))

    assert len(findings) == 1
    assert findings[0].drift_type is DriftType.MODIFIED
    assert findings[0].identity.name == "internal.test|internal.test|SOA"


def test_non_apex_system_record_is_not_ignored() -> None:
    payload = _private_zone_live()
    payload["RecordSets"]["/hostedzone/ZPRIVATE"].append(
        {
            "Name": "delegated.internal.test.",
            "Type": "NS",
            "TTL": 300,
            "ResourceRecords": [{"Value": "ns-3.awsdns.test."}],
        }
    )
    expected = adapt_terraform_state_with_diagnostics(_private_zone_state()).snapshots

    findings = detect_drift(expected, adapt_boto3_inventory(payload))

    assert len(findings) == 1
    assert findings[0].drift_type is DriftType.UNMANAGED
    assert findings[0].identity.name == "internal.test|delegated.internal.test|NS"
