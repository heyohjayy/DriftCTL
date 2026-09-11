from driftctl.detector import detect_drift
from driftctl.models import ResourceCategory, ResourceIdentity, ResourceSnapshot


def snapshot(name: str, attributes: dict) -> ResourceSnapshot:
    return ResourceSnapshot(ResourceIdentity("aws", "security_group", name), ResourceCategory.NETWORKING, attributes)


def test_detector_emits_only_missing_unmanaged_and_modified() -> None:
    expected = [snapshot("missing", {"vpc_id": "vpc-1"}), snapshot("changed", {"vpc_id": "vpc-1"})]
    live = [snapshot("changed", {"vpc_id": "vpc-2"}), snapshot("unmanaged", {"vpc_id": "vpc-1"})]
    findings = detect_drift(expected, live)
    assert [(finding.drift_type.value, finding.identity.name) for finding in findings] == [("missing", "missing"), ("unmanaged", "unmanaged"), ("modified", "changed")]
    assert findings[2].changes == {"vpc_id": {"expected": "vpc-1", "live": "vpc-2"}}


def test_detector_ignores_order_of_equivalent_ingress_rules() -> None:
    first = snapshot("web", {"ingress": [{"from_port": 443}, {"from_port": 22}]})
    second = snapshot("web", {"ingress": [{"from_port": 22}, {"from_port": 443}]})
    assert detect_drift([first], [second]) == []
