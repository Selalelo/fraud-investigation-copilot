# One execution role per Lambda function (LLD.md sec 13's state machine), each scoped to
# exactly the resources it touches -- no shared "do everything" role.

locals {
  # function name -> list of extra IAM statements beyond basic Lambda logging (added below).
  # Every evidence-* function is read-only against nothing in this account (they represent
  # calls to internal bank systems that are out of scope for this POC's Terraform -- their
  # role exists so the state machine can invoke them, with no AWS-resource access granted).
  lambda_functions = {
    "dedup-merge" = {
      statements = [{
        actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Query"]
        resources = [aws_dynamodb_table.cases.arn, "${aws_dynamodb_table.cases.arn}/index/*"]
      }]
    }
    "evidence-customer"     = { statements = [] }
    "evidence-transaction"  = { statements = [] }
    "evidence-beneficiary"  = { statements = [] }
    "evidence-device"       = { statements = [] }
    "evidence-kyc"          = { statements = [] }
    "evidence-safps"        = { statements = [] }
    "snapshot-writer" = {
      statements = [{
        actions   = ["s3:PutObject", "s3:PutObjectRetention"]
        resources = ["${aws_s3_bucket.evidence_snapshots.arn}/*"]
      }]
    }
    "indicator-engine" = {
      statements = [{
        actions   = ["s3:GetObject"]
        resources = ["${aws_s3_bucket.evidence_snapshots.arn}/*"]
      }]
    }
    "entity-graph" = {
      statements = [{
        actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Query"]
        resources = [aws_dynamodb_table.entity_graph.arn]
      }]
    }
    "scenario-classifier" = { statements = [] }
    "llm-narrative" = {
      statements = [{
        actions   = ["bedrock:InvokeModel"]
        resources = ["arn:aws:bedrock:${var.aws_region}::foundation-model/*"]
      }]
    }
    "narrative-validator" = { statements = [] }
    "case-writer" = {
      statements = [{
        actions   = ["dynamodb:PutItem", "dynamodb:UpdateItem"]
        resources = [aws_dynamodb_table.cases.arn]
        }, {
        # Audit log: PutItem only -- no UpdateItem/DeleteItem, enforcing append-only (LLD sec 11)
        actions   = ["dynamodb:PutItem"]
        resources = [aws_dynamodb_table.audit_log.arn]
      }]
    }
    "alert-dlq-writer" = {
      statements = [{
        actions   = ["sqs:SendMessage"]
        resources = [aws_sqs_queue.alert_dlq.arn]
      }]
    }
    "duplicate-logger" = {
      statements = [{
        actions   = ["dynamodb:PutItem"]
        resources = [aws_dynamodb_table.audit_log.arn]
      }]
    }
  }
}

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  for_each           = local.lambda_functions
  name               = "${var.name_prefix}-${each.key}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "lambda_basic_logging" {
  for_each   = local.lambda_functions
  role       = aws_iam_role.lambda[each.key].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_extra" {
  for_each = { for k, v in local.lambda_functions : k => v if length(v.statements) > 0 }
  name     = "${var.name_prefix}-${each.key}-policy"
  role     = aws_iam_role.lambda[each.key].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      for s in each.value.statements : {
        Effect   = "Allow"
        Action   = s.actions
        Resource = s.resources
      }
    ]
  })
}

# KMS decrypt/encrypt for every Lambda role that touches S3/DynamoDB (least privilege: grant
# key use only to roles that actually read/write encrypted data, not every Lambda).
resource "aws_iam_role_policy" "kms_access" {
  for_each = toset([
    "dedup-merge", "snapshot-writer", "indicator-engine", "case-writer", "duplicate-logger",
    "entity-graph",
  ])
  name = "${var.name_prefix}-${each.key}-kms"
  role = aws_iam_role.lambda[each.key].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey"]
      Resource = aws_kms_key.main.arn
    }]
  })
}

# Step Functions execution role -- only permission to invoke this stack's own Lambdas.
resource "aws_iam_role" "step_functions" {
  name = "${var.name_prefix}-state-machine-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "states.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "step_functions_invoke" {
  name = "${var.name_prefix}-state-machine-invoke"
  role = aws_iam_role.step_functions.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = [for f in aws_lambda_function.functions : f.arn]
    }]
  })
}

# Step Functions execution logging uses AWS's log-delivery mechanism, which requires these
# specific actions on the role (not just CloudWatch Logs write access) -- per AWS's documented
# requirement for aws_sfn_state_machine logging_configuration.
resource "aws_iam_role_policy" "step_functions_logging" {
  name = "${var.name_prefix}-state-machine-logging"
  role = aws_iam_role.step_functions.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "logs:CreateLogDelivery", "logs:GetLogDelivery", "logs:UpdateLogDelivery",
        "logs:DeleteLogDelivery", "logs:ListLogDeliveries", "logs:PutResourcePolicy",
        "logs:DescribeResourcePolicies", "logs:DescribeLogGroups",
      ]
      Resource = "*" # AWS requires "*" for this specific log-delivery API set
    }]
  })
}
