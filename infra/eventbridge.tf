# Fraud engine alert ingestion (HLD.md sec 3). The bank's fraud engine publishes to this event
# bus; a rule forwards matching events to the SQS buffer.

resource "aws_cloudwatch_event_bus" "fraud_alerts" {
  name = "${var.name_prefix}-fraud-alerts"
}

resource "aws_cloudwatch_event_rule" "fraud_alert" {
  name           = "${var.name_prefix}-fraud-alert-rule"
  event_bus_name = aws_cloudwatch_event_bus.fraud_alerts.name
  event_pattern = jsonencode({
    "detail-type" = ["FraudAlert"]
  })
}

resource "aws_cloudwatch_event_target" "to_sqs" {
  rule           = aws_cloudwatch_event_rule.fraud_alert.name
  event_bus_name = aws_cloudwatch_event_bus.fraud_alerts.name
  arn            = aws_sqs_queue.alerts.arn

  sqs_target {
    message_group_id = "fraud-alert"
  }
}
