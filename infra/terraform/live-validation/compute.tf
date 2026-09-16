data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_security_group" "ec2_validation" {
  count       = var.enable_ec2_validation_instance ? 1 : 0
  name        = "${var.validation_prefix}-ec2-sg"
  description = "No-inbound security group for the optional DriftCTL EC2 validation fixture"
  vpc_id      = aws_vpc.validation.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${var.validation_prefix}-ec2-sg"
  })
}

resource "aws_instance" "validation" {
  count                       = var.enable_ec2_validation_instance ? 1 : 0
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = var.ec2_instance_type
  subnet_id                   = aws_subnet.public_primary.id
  associate_public_ip_address = true
  iam_instance_profile        = aws_iam_instance_profile.ec2_validation.name
  vpc_security_group_ids      = [aws_security_group.ec2_validation[0].id]

  tags = merge(local.common_tags, {
    Name = "${var.validation_prefix}-ec2"
  })
}
