from driftctl.adapters.boto3_snapshots import adapt_boto3_inventory
from driftctl.adapters.terraform_state import adapt_terraform_state_with_diagnostics
from driftctl.detector import detect_drift
from driftctl.models import DriftType, Severity
from driftctl.presentation import ImpactLevel, assess_impacts, readable_resource_type
from driftctl.scoping import filter_snapshots_by_tag_scope
from driftctl.severity_rules import classify_finding, default_rules


LB_ARN = "arn:aws:elasticloadbalancing:eu-west-1:123456789012:loadbalancer/app/app-lb/abc"
TG_ARN = "arn:aws:elasticloadbalancing:eu-west-1:123456789012:targetgroup/app-tg/def"
LISTENER_ARN = "arn:aws:elasticloadbalancing:eu-west-1:123456789012:listener/app/app-lb/abc/ghi"


def _state() -> dict:
    tags = {"Name": "app-lb", "Project": "Test"}
    return {"values": {"root_module": {"resources": [
        {"address": "aws_nat_gateway.main", "mode": "managed", "type": "aws_nat_gateway", "name": "main", "values": {"id": "nat-1", "vpc_id": "vpc-1", "subnet_id": "subnet-1", "allocation_id": "eipalloc-1", "connectivity_type": "public", "state": "available", "tags": {"Name": "app-nat", "Project": "Test"}}},
        {"address": "aws_lb.main", "mode": "managed", "type": "aws_lb", "name": "main", "values": {"id": "app-lb", "arn": LB_ARN, "name": "app-lb", "load_balancer_type": "application", "internal": False, "ip_address_type": "ipv4", "subnets": ["subnet-1", "subnet-2"], "security_groups": ["sg-1"], "tags": tags}},
        {"address": "aws_lb_target_group.main", "mode": "managed", "type": "aws_lb_target_group", "name": "main", "values": {"id": "app-tg", "arn": TG_ARN, "name": "app-tg", "vpc_id": "vpc-1", "protocol": "HTTP", "port": 80, "target_type": "instance", "health_check": [{"enabled": True, "protocol": "HTTP", "port": "traffic-port", "path": "/health", "interval": 30, "timeout": 5, "healthy_threshold": 5, "unhealthy_threshold": 2, "matcher": "200"}], "tags": {"Name": "app-tg", "Project": "Test"}}},
        {"address": "aws_lb_listener.https", "mode": "managed", "type": "aws_lb_listener", "name": "https", "values": {"arn": LISTENER_ARN, "load_balancer_arn": LB_ARN, "protocol": "HTTPS", "port": 443, "ssl_policy": "ELBSecurityPolicy-TLS13-1-2-2021-06", "certificate_arn": "arn:aws:acm:eu-west-1:123456789012:certificate/cert", "default_action": [{"type": "forward", "target_group_arn": TG_ARN}]}},
        {"address": "aws_lb_listener_rule.api", "mode": "managed", "type": "aws_lb_listener_rule", "name": "api", "values": {"listener_arn": LISTENER_ARN, "priority": 10, "condition": [{"path_pattern": [{"values": ["/api/*"]}]}], "action": [{"type": "forward", "target_group_arn": TG_ARN}]}},
        {"address": "aws_db_instance.main", "mode": "managed", "type": "aws_db_instance", "name": "main", "values": {"id": "app-db", "engine": "postgres", "engine_version": "16.3", "instance_class": "db.t4g.micro", "allocated_storage": 20, "storage_type": "gp3", "storage_encrypted": True, "publicly_accessible": False, "vpc_security_group_ids": ["sg-db"], "db_subnet_group_name": "app-db-subnets", "backup_retention_period": 7, "deletion_protection": True, "multi_az": False, "port": 5432, "copy_tags_to_snapshot": True, "tags": {"Name": "app-db", "Project": "Test"}}},
    ]}}}


def _live() -> dict:
    project = [{"Key": "Project", "Value": "Test"}]
    return {
        "NatGateways": [{"NatGatewayId": "nat-1", "VpcId": "vpc-1", "SubnetId": "subnet-1", "ConnectivityType": "public", "State": "available", "NatGatewayAddresses": [{"AllocationId": "eipalloc-1"}], "Tags": [{"Key": "Name", "Value": "app-nat"}, *project]}],
        "LoadBalancers": [{"LoadBalancerArn": LB_ARN, "LoadBalancerName": "app-lb", "Type": "application", "Scheme": "internet-facing", "IpAddressType": "ipv4", "AvailabilityZones": [{"SubnetId": "subnet-2"}, {"SubnetId": "subnet-1"}], "SecurityGroups": ["sg-1"], "Tags": [{"Key": "Name", "Value": "app-lb"}, *project]}],
        "TargetGroups": [{"TargetGroupArn": TG_ARN, "TargetGroupName": "app-tg", "VpcId": "vpc-1", "Protocol": "HTTP", "Port": 80, "TargetType": "instance", "HealthCheckEnabled": True, "HealthCheckProtocol": "HTTP", "HealthCheckPort": "traffic-port", "HealthCheckPath": "/health", "HealthCheckIntervalSeconds": 30, "HealthCheckTimeoutSeconds": 5, "HealthyThresholdCount": 5, "UnhealthyThresholdCount": 2, "Matcher": {"HttpCode": "200"}, "Tags": [{"Key": "Name", "Value": "app-tg"}, *project]}],
        "Listeners": {LB_ARN: [{"ListenerArn": LISTENER_ARN, "Protocol": "HTTPS", "Port": 443, "SslPolicy": "ELBSecurityPolicy-TLS13-1-2-2021-06", "Certificates": [{"CertificateArn": "arn:aws:acm:eu-west-1:123456789012:certificate/cert", "IsDefault": True}], "DefaultActions": [{"Type": "forward", "TargetGroupArn": TG_ARN}]}]},
        "ListenerRules": {LISTENER_ARN: [{"RuleArn": f"{LISTENER_ARN}/default", "Priority": "default", "IsDefault": True, "Conditions": [], "Actions": [{"Type": "forward", "TargetGroupArn": TG_ARN}]}, {"RuleArn": f"{LISTENER_ARN}/rule", "Priority": "10", "IsDefault": False, "Conditions": [{"Field": "path-pattern", "PathPatternConfig": {"Values": ["/api/*"]}}], "Actions": [{"Type": "forward", "TargetGroupArn": TG_ARN}]}]},
        "DBInstances": [{"DBInstanceIdentifier": "app-db", "Engine": "postgres", "EngineVersion": "16.3", "DBInstanceClass": "db.t4g.micro", "AllocatedStorage": 20, "StorageType": "gp3", "StorageEncrypted": True, "PubliclyAccessible": False, "VpcSecurityGroups": [{"VpcSecurityGroupId": "sg-db"}], "DBSubnetGroup": {"DBSubnetGroupName": "app-db-subnets"}, "BackupRetentionPeriod": 7, "DeletionProtection": True, "MultiAZ": False, "Endpoint": {"Port": 5432}, "CopyTagsToSnapshot": True, "Tags": [{"Key": "Name", "Value": "app-db"}, *project]}],
    }


def test_sprint3b_matching_normalized_inventory_has_no_drift() -> None:
    expected = adapt_terraform_state_with_diagnostics(_state()).snapshots
    assert detect_drift(expected, adapt_boto3_inventory(_live())) == []


def test_sprint3b_representative_changes_are_modified() -> None:
    live = _live()
    live["NatGateways"][0]["State"] = "failed"
    live["LoadBalancers"][0]["Scheme"] = "internal"
    live["DBInstances"][0]["AllocatedStorage"] = 50

    findings = detect_drift(adapt_terraform_state_with_diagnostics(_state()).snapshots, adapt_boto3_inventory(live))

    assert {(finding.identity.resource_type, finding.drift_type) for finding in findings} == {
        ("nat_gateway", DriftType.MODIFIED),
        ("application_load_balancer", DriftType.MODIFIED),
        ("rds_db_instance", DriftType.MODIFIED),
    }


def test_tag_scope_keeps_in_scope_unmanaged_and_excludes_outside_resources() -> None:
    live = _live()
    live["NatGateways"] = [
        {"NatGatewayId": "nat-in", "VpcId": "vpc-1", "SubnetId": "subnet-1", "State": "available", "Tags": [{"Key": "Project", "Value": "Test"}]},
        {"NatGatewayId": "nat-out", "VpcId": "vpc-2", "SubnetId": "subnet-2", "State": "available", "Tags": [{"Key": "Project", "Value": "Other"}]},
    ]
    scoped = filter_snapshots_by_tag_scope(adapt_boto3_inventory(live), {"Project": "Test"})
    nat_gateways = [snapshot for snapshot in scoped if snapshot.identity.resource_type == "nat_gateway"]

    findings = detect_drift([], nat_gateways)

    assert [finding.identity.name for finding in findings] == ["nat-in"]
    assert findings[0].drift_type is DriftType.UNMANAGED


def test_listener_default_rule_is_provider_default_but_user_rule_is_preserved() -> None:
    rules = [snapshot for snapshot in adapt_boto3_inventory(_live()) if snapshot.identity.resource_type == "load_balancer_listener_rule"]

    assert [snapshot.identity.name for snapshot in rules] == ["app-lb|HTTPS|443|10"]
    assert rules[0].attributes["tags"]["Project"] == "Test"


def test_public_rds_has_specific_severity_impact_and_display_name() -> None:
    live = _live(); live["DBInstances"][0]["PubliclyAccessible"] = True
    findings = detect_drift(adapt_terraform_state_with_diagnostics(_state()).snapshots, adapt_boto3_inventory(live))
    finding = next(item for item in findings if item.identity.resource_type == "rds_db_instance")

    classify_finding(finding, default_rules())
    impact = assess_impacts(finding)

    assert finding.severity is Severity.SEVERE
    assert impact.security is ImpactLevel.HIGH
    assert impact.availability is ImpactLevel.NOT_ASSESSED
    assert readable_resource_type("rds_db_instance") == "AWS RDS DB Instance"
