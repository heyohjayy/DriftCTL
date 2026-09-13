locals {
  sprint3_tags = {
    Project = "DriftCTL-Sprint3"
    Name    = "driftctl-sprint3"
  }
}

resource "aws_vpc" "sprint3" {
  cidr_block           = "10.30.0.0/16"
  enable_dns_hostnames = true
  tags                 = merge(local.sprint3_tags, { Name = "driftctl-sprint3-vpc" })
}

resource "aws_subnet" "sprint3_a" {
  vpc_id            = aws_vpc.sprint3.id
  cidr_block        = "10.30.1.0/24"
  availability_zone = "${var.aws_region}a"
  tags              = merge(local.sprint3_tags, { Name = "driftctl-sprint3-a" })
}

resource "aws_subnet" "sprint3_b" {
  vpc_id            = aws_vpc.sprint3.id
  cidr_block        = "10.30.2.0/24"
  availability_zone = "${var.aws_region}b"
  tags              = merge(local.sprint3_tags, { Name = "driftctl-sprint3-b" })
}

resource "aws_internet_gateway" "sprint3" {
  vpc_id = aws_vpc.sprint3.id
  tags   = merge(local.sprint3_tags, { Name = "driftctl-sprint3-igw" })
}

resource "aws_route_table" "sprint3" {
  vpc_id = aws_vpc.sprint3.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.sprint3.id
  }
  tags = merge(local.sprint3_tags, { Name = "driftctl-sprint3-route-table" })
}

resource "aws_route_table_association" "sprint3_a" {
  subnet_id      = aws_subnet.sprint3_a.id
  route_table_id = aws_route_table.sprint3.id
}

resource "aws_route_table_association" "sprint3_b" {
  subnet_id      = aws_subnet.sprint3_b.id
  route_table_id = aws_route_table.sprint3.id
}

resource "aws_network_acl" "sprint3" {
  vpc_id     = aws_vpc.sprint3.id
  subnet_ids = [aws_subnet.sprint3_a.id, aws_subnet.sprint3_b.id]
  ingress {
    protocol   = "tcp"
    rule_no    = 100
    action     = "allow"
    cidr_block = "10.30.0.0/16"
    from_port  = 443
    to_port    = 443
  }
  egress {
    protocol   = "-1"
    rule_no    = 100
    action     = "allow"
    cidr_block = "0.0.0.0/0"
    from_port  = 0
    to_port    = 0
  }
  tags = merge(local.sprint3_tags, { Name = "driftctl-sprint3-nacl" })
}

data "aws_iam_policy_document" "sprint3_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "sprint3" {
  name               = "driftctl-sprint3-role"
  assume_role_policy = data.aws_iam_policy_document.sprint3_assume_role.json
  tags               = merge(local.sprint3_tags, { Name = "driftctl-sprint3-role" })
}

resource "aws_iam_role_policy_attachment" "sprint3_read_only" {
  role       = aws_iam_role.sprint3.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

resource "aws_iam_instance_profile" "sprint3" {
  name = "driftctl-sprint3-profile"
  role = aws_iam_role.sprint3.name
  tags = merge(local.sprint3_tags, { Name = "driftctl-sprint3-profile" })
}

resource "aws_route53_zone" "sprint3" {
  count = var.enable_sprint3_route53 ? 1 : 0
  name  = var.sprint3_route53_zone_name
  tags  = merge(local.sprint3_tags, { Name = "driftctl-sprint3-zone" })
}

resource "aws_route53_record" "sprint3" {
  count   = var.enable_sprint3_route53 ? 1 : 0
  zone_id = aws_route53_zone.sprint3[0].zone_id
  name    = "health.${aws_route53_zone.sprint3[0].name}"
  type    = "A"
  ttl     = 60
  records = ["192.0.2.10"]
}
