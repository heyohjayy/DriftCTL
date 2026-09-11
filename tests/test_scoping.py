from driftctl.adapters.boto3_snapshots import adapt_boto3_inventory
from driftctl.detector import detect_drift
from driftctl.models import ResourceCategory, ResourceIdentity, ResourceSnapshot
from driftctl.scoping import filter_snapshots_by_tag_scope, parse_tag_scope


def _live_inventory() -> dict:
    return {
        "SecurityGroups": [
            {"GroupId": "sg-managed", "GroupName": "managed", "VpcId": "vpc-1", "IpPermissions": [], "IpPermissionsEgress": [], "Tags": [{"Key": "Project", "Value": "Test"}]},
            {"GroupId": "sg-unmanaged", "GroupName": "unmanaged", "VpcId": "vpc-1", "IpPermissions": [], "IpPermissionsEgress": [], "Tags": [{"Key": "Project", "Value": "Test"}]},
            {"GroupId": "sg-other", "GroupName": "other", "VpcId": "vpc-1", "IpPermissions": [], "IpPermissionsEgress": [], "Tags": [{"Key": "Project", "Value": "Other"}]},
        ],
        "Reservations": [{"Instances": [
            {"InstanceId": "i-scoped", "ImageId": "ami-1", "InstanceType": "t3.micro", "SubnetId": "subnet-1", "SecurityGroups": [], "Tags": [{"Key": "Name", "Value": "scoped"}, {"Key": "Project", "Value": "Test"}]},
            {"InstanceId": "i-other", "ImageId": "ami-1", "InstanceType": "t3.micro", "SubnetId": "subnet-1", "SecurityGroups": [], "Tags": [{"Key": "Name", "Value": "other"}, {"Key": "Project", "Value": "Other"}]},
        ]}],
    }


def test_tag_scope_excludes_unrelated_live_instances_and_security_groups() -> None:
    scoped = filter_snapshots_by_tag_scope(adapt_boto3_inventory(_live_inventory()), parse_tag_scope(["Project=Test"]))

    assert {snapshot.identity.name for snapshot in scoped} == {"managed", "unmanaged", "scoped"}


def test_in_scope_unmanaged_resource_is_detected() -> None:
    live = filter_snapshots_by_tag_scope(adapt_boto3_inventory(_live_inventory()), {"Project": "Test"})
    expected = [
        ResourceSnapshot(
            ResourceIdentity("aws", "security_group", "managed"),
            ResourceCategory.NETWORKING,
            {"vpc_id": "vpc-1", "ingress": [], "egress": [], "tags": {"Project": "Test"}},
        ),
        ResourceSnapshot(
            ResourceIdentity("aws", "instance", "scoped"),
            ResourceCategory.COMPUTE,
            {"instance_type": "t3.micro", "ami": "ami-1", "subnet_id": "subnet-1", "associate_public_ip_address": False, "security_group_ids": [], "tags": {"Name": "scoped", "Project": "Test"}},
        ),
    ]

    findings = detect_drift(expected, live)

    assert [(finding.drift_type.value, finding.identity.name) for finding in findings] == [("unmanaged", "unmanaged")]


def test_no_scope_preserves_whole_region_inventory() -> None:
    snapshots = adapt_boto3_inventory(_live_inventory())

    assert filter_snapshots_by_tag_scope(snapshots, {}) == snapshots
