locals {
  validation_tags = {
    Project = "DriftCTL-Validation"
    Name    = "driftctl-validation"
  }
}

resource "aws_vpc" "validation" {
  cidr_block           = "10.30.0.0/16"
  enable_dns_hostnames = true
  tags                 = merge(local.validation_tags, { Name = "driftctl-validation-vpc" })
}

resource "aws_subnet" "validation_a" {
  vpc_id            = aws_vpc.validation.id
  cidr_block        = "10.30.1.0/24"
  availability_zone = "${var.aws_region}a"
  tags              = merge(local.validation_tags, { Name = "driftctl-validation-a" })
}

resource "aws_subnet" "validation_b" {
  vpc_id            = aws_vpc.validation.id
  cidr_block        = "10.30.2.0/24"
  availability_zone = "${var.aws_region}b"
  tags              = merge(local.validation_tags, { Name = "driftctl-validation-b" })
}

resource "aws_internet_gateway" "validation" {
  vpc_id = aws_vpc.validation.id
  tags   = merge(local.validation_tags, { Name = "driftctl-validation-igw" })
}

resource "aws_route_table" "validation" {
  vpc_id = aws_vpc.validation.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.validation.id
  }
  tags = merge(local.validation_tags, { Name = "driftctl-validation-route-table" })
}

resource "aws_route_table_association" "validation_a" {
  subnet_id      = aws_subnet.validation_a.id
  route_table_id = aws_route_table.validation.id
}

resource "aws_route_table_association" "validation_b" {
  subnet_id      = aws_subnet.validation_b.id
  route_table_id = aws_route_table.validation.id
}

resource "aws_network_acl" "validation" {
  vpc_id     = aws_vpc.validation.id
  subnet_ids = [aws_subnet.validation_a.id, aws_subnet.validation_b.id]
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
  tags = merge(local.validation_tags, { Name = "driftctl-validation-nacl" })
}

data "aws_iam_policy_document" "validation_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "validation" {
  name               = "driftctl-validation-role"
  assume_role_policy = data.aws_iam_policy_document.validation_assume_role.json
  tags               = merge(local.validation_tags, { Name = "driftctl-validation-role" })
}

resource "aws_iam_role_policy_attachment" "validation_read_only" {
  role       = aws_iam_role.validation.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

resource "aws_iam_instance_profile" "validation" {
  name = "driftctl-validation-profile"
  role = aws_iam_role.validation.name
  tags = merge(local.validation_tags, { Name = "driftctl-validation-profile" })
}

resource "aws_route53_zone" "validation" {
  count = var.enable_validation_route53 ? 1 : 0
  name  = var.validation_route53_zone_name
  tags  = merge(local.validation_tags, { Name = "driftctl-validation-zone" })
}

resource "aws_route53_record" "validation" {
  count   = var.enable_validation_route53 ? 1 : 0
  zone_id = aws_route53_zone.validation[0].zone_id
  name    = "health.${aws_route53_zone.validation[0].name}"
  type    = "A"
  ttl     = 60
  records = ["192.0.2.10"]
}
