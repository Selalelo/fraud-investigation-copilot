output "state_machine_arn" {
  value = aws_sfn_state_machine.case_pipeline.arn
}

output "event_bus_name" {
  value = aws_cloudwatch_event_bus.fraud_alerts.name
}

output "cases_table_name" {
  value = aws_dynamodb_table.cases.name
}

output "audit_log_table_name" {
  value = aws_dynamodb_table.audit_log.name
}

output "evidence_bucket_name" {
  value = aws_s3_bucket.evidence_snapshots.bucket
}

output "entity_graph_table_name" {
  value = aws_dynamodb_table.entity_graph.name
}

output "kms_key_arn" {
  value = aws_kms_key.main.arn
}
