# Case store (LLD.md sec 6). On-demand billing -- avoids idle provisioned-capacity cost for a
# POC with unpredictable, low traffic.

resource "aws_dynamodb_table" "cases" {
  name         = "${var.name_prefix}-cases"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "case_id"

  attribute {
    name = "case_id"
    type = "S"
  }

  attribute {
    name = "customer_id"
    type = "S"
  }

  global_secondary_index {
    name            = "customer_id-index"
    hash_key        = "customer_id"
    projection_type = "ALL"
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.main.arn
  }

  point_in_time_recovery {
    enabled = true
  }
}

# Append-only audit table (LLD.md sec 11) -- no update/delete IAM permission is ever granted to
# any role (see iam.tf), enforcing append-only at the access-control layer.
resource "aws_dynamodb_table" "audit_log" {
  name         = "${var.name_prefix}-audit-log"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "case_id"
  range_key    = "decided_at"

  attribute {
    name = "case_id"
    type = "S"
  }

  attribute {
    name = "decided_at"
    type = "S"
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.main.arn
  }

  point_in_time_recovery {
    enabled = true
  }
}

# Entity graph (LLD.md sec 7), substituted for Neptune in this POC -- near-zero cost on-demand
# vs. Neptune's ~$100-150/mo always-on instance, and removes the VPC networking Neptune would've
# required. Adjacency-list pattern: pk = "<node_type>#<node_id>", sk = "<node_type>#<node_id>"
# of the neighbor, with edge_type/prior_case_count as regular attributes. The design's own
# stated intent ("model it so it maps to Neptune later" -- HLD.md sec 7.1) is preserved: swapping
# this table for a real Neptune driver later changes only where nodes/edges are read and
# written, not the query shape (1-2 hop traversal from a starting node).
resource "aws_dynamodb_table" "entity_graph" {
  name         = "${var.name_prefix}-entity-graph"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.main.arn
  }

  point_in_time_recovery {
    enabled = true
  }
}
