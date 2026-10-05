terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }

  # Local state file for this POC -- no remote state backend (S3+DynamoDB lock table) needed
  # at this scale; revisit if this stack grows beyond a single operator.
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "fraud-copilot"
      Environment = "poc"
      ManagedBy   = "terraform"
    }
  }
}
