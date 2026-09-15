from datetime import datetime, timezone

import boto3
from botocore.stub import Stubber

from driftctl.adapters.boto3_snapshots import adapt_boto3_inventory
from driftctl.collectors.aws import AwsInventoryCollector


def test_collects_boto3_shaped_inventory_with_read_only_calls() -> None:
    session = boto3.Session(
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        region_name="us-east-1",
    )
    ec2 = session.client("ec2")
    s3 = session.client("s3")
    ec2_stubber = Stubber(ec2)
    s3_stubber = Stubber(s3)
    ec2_stubber.add_response("describe_security_groups", {"SecurityGroups": [{"GroupId": "sg-0123", "GroupName": "web", "VpcId": "vpc-0123", "IpPermissions": []}]})
    ec2_stubber.add_response("describe_instances", {"Reservations": [{"ReservationId": "r-0123", "Instances": [{"InstanceId": "i-0123", "ImageId": "ami-0123", "InstanceType": "t3.micro", "SubnetId": "subnet-0123", "SecurityGroups": [], "Tags": [{"Key": "Name", "Value": "api"}]}]}]})
    for operation, key in [("describe_vpcs", "Vpcs"), ("describe_subnets", "Subnets"), ("describe_internet_gateways", "InternetGateways"), ("describe_route_tables", "RouteTables"), ("describe_network_acls", "NetworkAcls"), ("describe_nat_gateways", "NatGateways")]:
        ec2_stubber.add_response(operation, {key: []})
    s3_stubber.add_response("list_buckets", {"Buckets": [{"Name": "example-bucket", "CreationDate": datetime(2026, 1, 1, tzinfo=timezone.utc)}]})
    s3_stubber.add_response("get_public_access_block", {"PublicAccessBlockConfiguration": {"BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True}}, {"Bucket": "example-bucket"})
    s3_stubber.add_response("get_bucket_encryption", {"ServerSideEncryptionConfiguration": {"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]}}, {"Bucket": "example-bucket"})
    s3_stubber.add_response("get_bucket_tagging", {"TagSet": [{"Key": "ManagedBy", "Value": "Terraform"}]}, {"Bucket": "example-bucket"})

    with ec2_stubber, s3_stubber:
        inventory = AwsInventoryCollector(ec2, s3).collect()

    assert inventory["SecurityGroups"][0]["GroupName"] == "web"
    assert inventory["Buckets"][0]["BucketEncryption"]["Rules"][0]["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"] == "AES256"
    assert inventory["Reservations"][0]["Instances"][0]["InstanceId"] == "i-0123"
    assert len(adapt_boto3_inventory(inventory)) == 3


def test_tag_scope_is_sent_to_ec2_collection_calls() -> None:
    session = boto3.Session(
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        region_name="us-east-1",
    )
    ec2 = session.client("ec2")
    s3 = session.client("s3")
    ec2_stubber = Stubber(ec2)
    s3_stubber = Stubber(s3)
    filters = {"Filters": [{"Name": "tag:Project", "Values": ["Test"]}]}
    ec2_stubber.add_response("describe_security_groups", {"SecurityGroups": [{"GroupId": "sg-scoped", "GroupName": "scoped", "VpcId": "vpc-0123", "IpPermissions": [], "Tags": [{"Key": "Project", "Value": "Test"}]}]}, filters)
    ec2_stubber.add_response("describe_instances", {"Reservations": [{"ReservationId": "r-scoped", "Instances": [{"InstanceId": "i-scoped", "ImageId": "ami-0123", "InstanceType": "t3.micro", "SubnetId": "subnet-0123", "SecurityGroups": [], "Tags": [{"Key": "Project", "Value": "Test"}]}]}]}, filters)
    for operation, key in [("describe_vpcs", "Vpcs"), ("describe_subnets", "Subnets"), ("describe_internet_gateways", "InternetGateways"), ("describe_route_tables", "RouteTables"), ("describe_network_acls", "NetworkAcls"), ("describe_nat_gateways", "NatGateways")]:
        ec2_stubber.add_response(operation, {key: []}, filters)
    s3_stubber.add_response("list_buckets", {"Buckets": []})

    with ec2_stubber, s3_stubber:
        inventory = AwsInventoryCollector(ec2, s3).collect({"Project": "Test"})

    assert [group["GroupId"] for group in inventory["SecurityGroups"]] == ["sg-scoped"]
    assert [instance["InstanceId"] for instance in inventory["Reservations"][0]["Instances"]] == ["i-scoped"]
