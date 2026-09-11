# Sprint 2 Architecture

```text
Terraform fixture or CLI       boto3 fixture or AWS read APIs
          |                              |
          v                              v
 Terraform adapter                 boto3 adapter
          \                              /
           v                            v
             normalized ResourceSnapshot
                        |
                        v
               detector: missing | unmanaged | modified
                        |
                        v
             ordered, composable severity rules
                        |
             Markdown report + append-only JSONL audit log
```

The detector has no dependency on Terraform state or boto3 response structure. Terraform-specific S3 public-access and encryption resources are joined to their logical S3 bucket during adaptation. The CLI is intentionally read-only: remediation is a recommendation, never an API or Terraform apply. The AWS collector uses EC2 `Describe*` and S3 `List*`/`Get*` methods only.
