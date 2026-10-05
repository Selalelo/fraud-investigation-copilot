# A custom key policy is required here -- CloudWatch Logs and CloudTrail both need explicit
# key-policy statements to use a CMK for encryption; IAM role permissions on the key are not
# sufficient on their own (this is a real requirement discovered when CreateLogGroup and
# CreateTrail both failed with "KMS key does not exist or is not allowed to be used" against
# the default key policy).
data "aws_iam_policy_document" "kms_key_policy" {
  statement {
    sid       = "EnableIAMUserPermissions"
    actions   = ["kms:*"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }

  statement {
    sid     = "AllowCloudWatchLogs"
    actions = ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:Describe*"]
    resources = ["*"]
    principals {
      type        = "Service"
      identifiers = ["logs.${var.aws_region}.amazonaws.com"]
    }
    condition {
      test     = "ArnLike"
      variable = "kms:EncryptionContext:aws:logs:arn"
      values   = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*"]
    }
  }

  statement {
    sid     = "AllowCloudTrail"
    actions = ["kms:GenerateDataKey*", "kms:Decrypt", "kms:DescribeKey"]
    resources = ["*"]
    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "kms:EncryptionContext:aws:cloudtrail:arn"
      values   = ["arn:aws:cloudtrail:${var.aws_region}:${data.aws_caller_identity.current.account_id}:trail/*"]
    }
  }
}

resource "aws_kms_key" "main" {
  description             = "${var.name_prefix} encryption key -- S3 evidence snapshots, DynamoDB case store"
  deletion_window_in_days = 7
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.kms_key_policy.json
}

resource "aws_kms_alias" "main" {
  name          = "alias/${var.name_prefix}"
  target_key_id = aws_kms_key.main.key_id
}
