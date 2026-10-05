# The Lambda functions from LLD.md sec 13's state machine. Placeholder handler code (see
# placeholder_lambda/handler.py) -- this proves the infrastructure wiring (Step Functions ->
# Lambda -> IAM -> CloudWatch Logs), not a full port of src/fraud_copilot/*.py.

data "archive_file" "placeholder" {
  type        = "zip"
  source_dir  = "${path.module}/placeholder_lambda"
  output_path = "${path.module}/.build/placeholder_lambda.zip"
}

resource "aws_cloudwatch_log_group" "lambda" {
  for_each          = local.lambda_functions
  name              = "/aws/lambda/${var.name_prefix}-${each.key}"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.main.arn
}

resource "aws_lambda_function" "functions" {
  for_each         = local.lambda_functions
  function_name    = "${var.name_prefix}-${each.key}"
  role             = aws_iam_role.lambda[each.key].arn
  handler          = "handler.handler"
  runtime          = "python3.12"
  timeout          = each.key == "llm-narrative" ? 10 : 2
  filename         = data.archive_file.placeholder.output_path
  source_code_hash = data.archive_file.placeholder.output_base64sha256

  environment {
    variables = {
      FUNCTION_NAME = each.key
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}
