resource "aws_route53_zone" "private" {
  name          = var.private_zone_name
  force_destroy = true

  vpc {
    vpc_id = aws_vpc.validation.id
  }

  tags = merge(local.common_tags, {
    Name = "${var.validation_prefix}-private-zone"
  })
}

resource "aws_route53_record" "api" {
  zone_id = aws_route53_zone.private.zone_id
  name    = "api.${var.private_zone_name}"
  type    = "A"
  ttl     = 60
  records = ["10.30.2.10"]
}
