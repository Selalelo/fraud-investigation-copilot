resource "aws_cloudwatch_log_group" "state_machine" {
  name              = "/aws/vendedlogs/states/${var.name_prefix}-case-pipeline"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.main.arn
}

resource "aws_sfn_state_machine" "case_pipeline" {
  name     = "${var.name_prefix}-case-pipeline"
  role_arn = aws_iam_role.step_functions.arn

  definition = templatefile("${path.module}/state_machine.json.tpl", {
    dedup_merge_arn          = aws_lambda_function.functions["dedup-merge"].arn
    duplicate_logger_arn     = aws_lambda_function.functions["duplicate-logger"].arn
    evidence_customer_arn    = aws_lambda_function.functions["evidence-customer"].arn
    evidence_transaction_arn = aws_lambda_function.functions["evidence-transaction"].arn
    evidence_beneficiary_arn = aws_lambda_function.functions["evidence-beneficiary"].arn
    evidence_device_arn      = aws_lambda_function.functions["evidence-device"].arn
    evidence_kyc_arn         = aws_lambda_function.functions["evidence-kyc"].arn
    evidence_safps_arn       = aws_lambda_function.functions["evidence-safps"].arn
    snapshot_writer_arn      = aws_lambda_function.functions["snapshot-writer"].arn
    indicator_engine_arn     = aws_lambda_function.functions["indicator-engine"].arn
    entity_graph_arn         = aws_lambda_function.functions["entity-graph"].arn
    scenario_classifier_arn  = aws_lambda_function.functions["scenario-classifier"].arn
    llm_narrative_arn        = aws_lambda_function.functions["llm-narrative"].arn
    narrative_validator_arn  = aws_lambda_function.functions["narrative-validator"].arn
    case_writer_arn          = aws_lambda_function.functions["case-writer"].arn
    alert_dlq_writer_arn     = aws_lambda_function.functions["alert-dlq-writer"].arn
  })

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.state_machine.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }
}
