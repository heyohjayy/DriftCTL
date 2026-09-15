from datetime import datetime, timezone

import boto3
from botocore.stub import Stubber

from driftctl.collectors.aws import AwsInventoryCollector


def _session() -> boto3.Session:
    return boto3.Session(aws_access_key_id="testing", aws_secret_access_key="testing", region_name="eu-west-1")


def test_nat_gateway_collection_uses_scoped_read_only_describe() -> None:
    ec2 = _session().client("ec2")
    stubber = Stubber(ec2)
    filters = {"Filters": [{"Name": "tag:Project", "Values": ["Test"]}]}
    stubber.add_response("describe_nat_gateways", {"NatGateways": [{"NatGatewayId": "nat-1", "State": "available", "SubnetId": "subnet-1", "VpcId": "vpc-1", "Tags": [{"Key": "Project", "Value": "Test"}]}]}, filters)

    with stubber:
        gateways = AwsInventoryCollector(ec2, None)._ec2("describe_nat_gateways", "NatGateways", {"Project": "Test"})

    assert [gateway["NatGatewayId"] for gateway in gateways] == ["nat-1"]


def test_alb_collection_filters_parents_and_inherits_scope_to_children() -> None:
    elbv2 = _session().client("elbv2")
    stubber = Stubber(elbv2)
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    lb_in = "arn:aws:elasticloadbalancing:eu-west-1:123456789012:loadbalancer/app/in/abc"
    lb_out = "arn:aws:elasticloadbalancing:eu-west-1:123456789012:loadbalancer/app/out/def"
    tg = "arn:aws:elasticloadbalancing:eu-west-1:123456789012:targetgroup/app/ghi"
    listener = "arn:aws:elasticloadbalancing:eu-west-1:123456789012:listener/app/in/abc/jkl"
    load_balancers = [
        {"LoadBalancerArn": lb_in, "DNSName": "in.example", "CanonicalHostedZoneId": "Z1", "CreatedTime": created, "LoadBalancerName": "in", "Scheme": "internet-facing", "VpcId": "vpc-1", "State": {"Code": "active"}, "Type": "application", "AvailabilityZones": [], "SecurityGroups": [], "IpAddressType": "ipv4"},
        {"LoadBalancerArn": lb_out, "DNSName": "out.example", "CanonicalHostedZoneId": "Z1", "CreatedTime": created, "LoadBalancerName": "out", "Scheme": "internal", "VpcId": "vpc-2", "State": {"Code": "active"}, "Type": "application", "AvailabilityZones": [], "SecurityGroups": [], "IpAddressType": "ipv4"},
    ]
    stubber.add_response("describe_load_balancers", {"LoadBalancers": load_balancers})
    stubber.add_response("describe_tags", {"TagDescriptions": [{"ResourceArn": lb_in, "Tags": [{"Key": "Project", "Value": "Test"}]}, {"ResourceArn": lb_out, "Tags": [{"Key": "Project", "Value": "Other"}]}]}, {"ResourceArns": [lb_in, lb_out]})
    stubber.add_response("describe_target_groups", {"TargetGroups": [{"TargetGroupArn": tg, "TargetGroupName": "app", "Protocol": "HTTP", "Port": 80, "VpcId": "vpc-1", "HealthCheckProtocol": "HTTP", "HealthCheckPort": "traffic-port", "HealthCheckEnabled": True, "TargetType": "instance"}]})
    stubber.add_response("describe_tags", {"TagDescriptions": [{"ResourceArn": tg, "Tags": [{"Key": "Project", "Value": "Test"}]}]}, {"ResourceArns": [tg]})
    stubber.add_response("describe_listeners", {"Listeners": [{"ListenerArn": listener, "LoadBalancerArn": lb_in, "Port": 80, "Protocol": "HTTP", "DefaultActions": [{"Type": "forward", "TargetGroupArn": tg}]}]}, {"LoadBalancerArn": lb_in})
    stubber.add_response("describe_rules", {"Rules": [{"RuleArn": f"{listener}/default", "Priority": "default", "IsDefault": True, "Conditions": [], "Actions": [{"Type": "forward", "TargetGroupArn": tg}]}]}, {"ListenerArn": listener})

    with stubber:
        inventory = AwsInventoryCollector(None, None, elbv2_client=elbv2)._load_balancing({"Project": "Test"})

    assert [item["LoadBalancerArn"] for item in inventory["LoadBalancers"]] == [lb_in]
    assert inventory["Listeners"][lb_in][0]["Tags"] == [{"Key": "Project", "Value": "Test"}]
    assert inventory["ListenerRules"][listener][0]["Tags"] == [{"Key": "Project", "Value": "Test"}]


def test_rds_collection_filters_instances_after_reading_tags() -> None:
    rds = _session().client("rds")
    stubber = Stubber(rds)
    db_in = "arn:aws:rds:eu-west-1:123456789012:db:in"
    db_out = "arn:aws:rds:eu-west-1:123456789012:db:out"
    stubber.add_response("describe_db_instances", {"DBInstances": [{"DBInstanceIdentifier": "in", "DBInstanceArn": db_in}, {"DBInstanceIdentifier": "out", "DBInstanceArn": db_out}]})
    stubber.add_response("list_tags_for_resource", {"TagList": [{"Key": "Project", "Value": "Test"}]}, {"ResourceName": db_in})
    stubber.add_response("list_tags_for_resource", {"TagList": [{"Key": "Project", "Value": "Other"}]}, {"ResourceName": db_out})

    with stubber:
        databases = AwsInventoryCollector(None, None, rds_client=rds)._db_instances({"Project": "Test"})

    assert [database["DBInstanceIdentifier"] for database in databases] == ["in"]
