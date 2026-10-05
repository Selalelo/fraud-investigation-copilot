# Alert buffer + dedup key (HLD.md sec 3). Content-based dedup is a coarse first pass -- the
# real idempotency/merge logic (LLD.md sec 2.1, delimited hash, open+closed case check) still
# runs inside the dedup-merge Lambda; SQS dedup only protects against exact-duplicate deliveries
# within its 5-minute window.

resource "aws_sqs_queue" "alert_dlq" {
  # Must be a FIFO queue too -- AWS requires a redrive policy's DLQ to be the same queue type
  # as its source queue (discovered when CreateQueue rejected a standard-queue DLQ for the
  # FIFO alerts queue below).
  name                      = "${var.name_prefix}-alert-dlq.fifo"
  fifo_queue                = true
  message_retention_seconds = 1209600 # 14 days
  kms_master_key_id         = aws_kms_key.main.key_id
}

resource "aws_sqs_queue" "alerts" {
  name                        = "${var.name_prefix}-alerts.fifo"
  fifo_queue                  = true
  content_based_deduplication = true
  visibility_timeout_seconds  = 60
  message_retention_seconds   = 86400
  kms_master_key_id           = aws_kms_key.main.key_id

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.alert_dlq.arn
    maxReceiveCount     = 3
  })
}

resource "aws_sqs_queue_policy" "alerts" {
  queue_url = aws_sqs_queue.alerts.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.alerts.arn
      Condition = {
        ArnEquals = { "aws:SourceArn" = aws_cloudwatch_event_rule.fraud_alert.arn }
      }
    }]
  })
}
