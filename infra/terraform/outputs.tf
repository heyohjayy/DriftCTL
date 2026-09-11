output "artifacts_bucket" { value = aws_s3_bucket.artifacts.bucket }
output "web_security_group_id" { value = aws_security_group.web.id }
