data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "validation" {
  cidr_block           = "10.30.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = merge(local.common_tags, {
    Name = "${var.validation_prefix}-vpc"
  })
}

resource "aws_subnet" "public_primary" {
  vpc_id                  = aws_vpc.validation.id
  cidr_block              = "10.30.1.0/24"
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true

  tags = merge(local.common_tags, {
    Name = "${var.validation_prefix}-public-subnet"
    Tier = "public"
  })
}

resource "aws_subnet" "private_primary" {
  vpc_id            = aws_vpc.validation.id
  cidr_block        = "10.30.2.0/24"
  availability_zone = data.aws_availability_zones.available.names[1]

  tags = merge(local.common_tags, {
    Name = "${var.validation_prefix}-private-subnet"
    Tier = "private"
  })
}

resource "aws_subnet" "public_secondary" {
  vpc_id                  = aws_vpc.validation.id
  cidr_block              = "10.30.3.0/24"
  availability_zone       = data.aws_availability_zones.available.names[1]
  map_public_ip_on_launch = true

  tags = merge(local.common_tags, {
    Name = "${var.validation_prefix}b-public-subnet-secondary"
    Tier = "public"
  })
}

resource "aws_subnet" "private_secondary" {
  vpc_id            = aws_vpc.validation.id
  cidr_block        = "10.30.4.0/24"
  availability_zone = data.aws_availability_zones.available.names[0]

  tags = merge(local.common_tags, {
    Name = "${var.validation_prefix}b-private-subnet-secondary"
    Tier = "private"
  })
}

resource "aws_internet_gateway" "validation" {
  vpc_id = aws_vpc.validation.id

  tags = merge(local.common_tags, {
    Name = "${var.validation_prefix}-igw"
  })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.validation.id

  tags = merge(local.common_tags, {
    Name = "${var.validation_prefix}-public-rt"
    Tier = "public"
  })
}

resource "aws_route" "public_default" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.validation.id
}

resource "aws_route_table_association" "public_primary" {
  subnet_id      = aws_subnet.public_primary.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "public_secondary" {
  subnet_id      = aws_subnet.public_secondary.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.validation.id

  tags = merge(local.common_tags, {
    Name = "${var.validation_prefix}-private-rt"
    Tier = "private"
  })
}

resource "aws_route_table_association" "private_primary" {
  subnet_id      = aws_subnet.private_primary.id
  route_table_id = aws_route_table.private.id
}

resource "aws_route_table_association" "private_secondary" {
  subnet_id      = aws_subnet.private_secondary.id
  route_table_id = aws_route_table.private.id
}

resource "aws_network_acl" "private" {
  vpc_id = aws_vpc.validation.id

  tags = merge(local.common_tags, {
    Name = "${var.validation_prefix}-private-nacl"
    Tier = "private"
  })
}

resource "aws_network_acl_rule" "private_inbound" {
  network_acl_id = aws_network_acl.private.id
  egress         = false
  protocol       = "-1"
  rule_action    = "allow"
  rule_number    = 100
  cidr_block     = "10.30.0.0/16"
}

resource "aws_network_acl_rule" "private_outbound" {
  network_acl_id = aws_network_acl.private.id
  egress         = true
  protocol       = "-1"
  rule_action    = "allow"
  rule_number    = 100
  cidr_block     = "0.0.0.0/0"
}

resource "aws_network_acl_association" "private_primary" {
  network_acl_id = aws_network_acl.private.id
  subnet_id      = aws_subnet.private_primary.id
}

resource "aws_network_acl_association" "private_secondary" {
  network_acl_id = aws_network_acl.private.id
  subnet_id      = aws_subnet.private_secondary.id
}
