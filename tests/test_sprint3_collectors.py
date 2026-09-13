from datetime import datetime, timezone

import boto3
from botocore.stub import Stubber

from driftctl.collectors.aws import AwsInventoryCollector


def test_network_collection_uses_taggable_ec2_read_apis() -> None:
    session = boto3.Session(aws_access_key_id="testing", aws_secret_access_key="testing", region_name="us-east-1")
    ec2, s3 = session.client("ec2"), session.client("s3")
    ec2_stub, s3_stub = Stubber(ec2), Stubber(s3)
    filters = {"Filters": [{"Name": "tag:Project", "Values": ["Test"]}]}
    for operation, key in [("describe_security_groups", "SecurityGroups"), ("describe_instances", "Reservations"), ("describe_vpcs", "Vpcs"), ("describe_subnets", "Subnets"), ("describe_internet_gateways", "InternetGateways"), ("describe_route_tables", "RouteTables"), ("describe_network_acls", "NetworkAcls")]: ec2_stub.add_response(operation, {key: []}, filters)
    s3_stub.add_response("list_buckets", {"Buckets": []})
    with ec2_stub, s3_stub: inventory = AwsInventoryCollector(ec2, s3).collect({"Project": "Test"})
    assert inventory["Vpcs"] == [] and inventory["NetworkAcls"] == []


def test_iam_and_route53_collectors_are_injectable_read_only_families() -> None:
    session = boto3.Session(aws_access_key_id="testing", aws_secret_access_key="testing", region_name="us-east-1")
    iam, route53 = session.client("iam"), session.client("route53")
    iam_stub, r53_stub = Stubber(iam), Stubber(route53)
    iam_stub.add_response("list_roles", {"Roles": []})
    iam_stub.add_response("list_instance_profiles", {"InstanceProfiles": []})
    r53_stub.add_response("list_hosted_zones", {"HostedZones": [], "Marker": "marker", "MaxItems": "100", "IsTruncated": False})
    ec2, s3 = session.client("ec2"), session.client("s3"); ec2_stub, s3_stub = Stubber(ec2), Stubber(s3)
    for operation, key in [("describe_security_groups", "SecurityGroups"), ("describe_instances", "Reservations"), ("describe_vpcs", "Vpcs"), ("describe_subnets", "Subnets"), ("describe_internet_gateways", "InternetGateways"), ("describe_route_tables", "RouteTables"), ("describe_network_acls", "NetworkAcls")]: ec2_stub.add_response(operation, {key: []})
    s3_stub.add_response("list_buckets", {"Buckets": []})
    with ec2_stub, s3_stub, iam_stub, r53_stub:
        inventory = AwsInventoryCollector(ec2, s3, iam, route53).collect()
    assert inventory["IamRoles"] == [] and inventory["HostedZones"] == []


def test_iam_tag_scope_uses_dedicated_role_and_profile_tag_apis() -> None:
    session = boto3.Session(aws_access_key_id="testing", aws_secret_access_key="testing", region_name="us-east-1")
    iam = session.client("iam")
    stubber = Stubber(iam)
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    def role(name: str) -> dict:
        return {"Path": "/", "RoleName": name, "RoleId": f"AROA{name:0<12}"[:16], "Arn": f"arn:aws:iam::123456789012:role/{name}", "CreateDate": created, "AssumeRolePolicyDocument": "{}"}
    def profile(name: str) -> dict:
        return {"Path": "/", "InstanceProfileName": name, "InstanceProfileId": f"AIPA{name:0<12}"[:16], "Arn": f"arn:aws:iam::123456789012:instance-profile/{name}", "CreateDate": created, "Roles": []}
    scoped_role, outside_role = role("scoped"), role("outside")
    stubber.add_response("list_roles", {"Roles": [scoped_role, outside_role], "IsTruncated": False})
    stubber.add_response("get_role", {"Role": role("scoped")}, {"RoleName": "scoped"})
    stubber.add_response("list_role_tags", {"Tags": [{"Key": "Project", "Value": "Test"}], "IsTruncated": False}, {"RoleName": "scoped"})
    stubber.add_response("list_attached_role_policies", {"AttachedPolicies": [], "IsTruncated": False}, {"RoleName": "scoped"})
    stubber.add_response("list_role_policies", {"PolicyNames": [], "IsTruncated": False}, {"RoleName": "scoped"})
    stubber.add_response("get_role", {"Role": role("outside")}, {"RoleName": "outside"})
    stubber.add_response("list_role_tags", {"Tags": [{"Key": "Project", "Value": "Other"}], "IsTruncated": False}, {"RoleName": "outside"})
    scoped_profile, outside_profile = profile("scoped"), profile("outside")
    stubber.add_response("list_instance_profiles", {"InstanceProfiles": [scoped_profile, outside_profile], "IsTruncated": False})
    stubber.add_response("get_instance_profile", {"InstanceProfile": scoped_profile}, {"InstanceProfileName": "scoped"})
    stubber.add_response("list_instance_profile_tags", {"Tags": [{"Key": "Project", "Value": "Test"}], "IsTruncated": False}, {"InstanceProfileName": "scoped"})
    stubber.add_response("get_instance_profile", {"InstanceProfile": outside_profile}, {"InstanceProfileName": "outside"})
    stubber.add_response("list_instance_profile_tags", {"Tags": [{"Key": "Project", "Value": "Other"}], "IsTruncated": False}, {"InstanceProfileName": "outside"})
    collector = AwsInventoryCollector(None, None, iam)
    with stubber:
        roles = collector._roles({"Project": "Test"})
        profiles = collector._profiles({"Project": "Test"})
    assert [item["RoleName"] for item in roles] == ["scoped"]
    assert [item["InstanceProfileName"] for item in profiles] == ["scoped"]
    assert any("outside" in item["message"] for item in collector.diagnostics)
