# Evidence snapshot storage -- write-once via S3 Object Lock (LLD.md sec 4), encrypted with the
# project CMK. Object Lock must be enabled at bucket creation and cannot be added later.

resource "aws_s3_bucket" "evidence_snapshots" {
  bucket              = "${var.name_prefix}-evidence-snapshots-${data.aws_caller_identity.current.account_id}"
  object_lock_enabled = true
}

resource "aws_s3_bucket_versioning" "evidence_snapshots" {
  # Object Lock requires versioning to be enabled
  bucket = aws_s3_bucket.evidence_snapshots.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_object_lock_configuration" "evidence_snapshots" {
  bucket = aws_s3_bucket.evidence_snapshots.id
  rule {
    default_retention {
      mode = "GOVERNANCE" # POC: GOVERNANCE (revocable by an authorised admin), not COMPLIANCE
      days = 2555         # ~7 years, a common regulatory retention baseline
    }
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "evidence_snapshots" {
  bucket = aws_s3_bucket.evidence_snapshots.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.main.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "evidence_snapshots" {
  bucket                  = aws_s3_bucket.evidence_snapshots.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "aws_caller_identity" "current" {}
