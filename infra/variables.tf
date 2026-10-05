variable "aws_region" {
  description = "AWS region. Design intent (LLD.md sec 3.12) was af-south-1 (Cape Town) for SA data residency, but that region's STS/service endpoints weren't reachable from this network (DNS resolution failure on sts.af-south-1.amazonaws.com), so this POC deploys to us-east-1 instead -- revisit for a real deployment where residency actually matters."
  type        = string
  default     = "us-east-1"
}

variable "name_prefix" {
  description = "Prefix applied to every resource name, so this POC's resources are trivially distinguishable from other projects in the same account."
  type        = string
  default     = "fraud-copilot"
}

variable "environment" {
  type    = string
  default = "poc"
}

variable "alert_merge_window_minutes" {
  description = "SQS message retention proxy for the alert merge window (LLD.md sec 2.1)."
  type        = number
  default     = 30
}
