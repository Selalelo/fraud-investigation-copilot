{
  "Comment": "Fraud Investigation Copilot - case build pipeline (LLD.md sec 13)",
  "StartAt": "DeduplicateAndMerge",
  "States": {
    "DeduplicateAndMerge": {
      "Type": "Task",
      "Resource": "${dedup_merge_arn}",
      "ResultPath": "$.dedupResult",
      "Next": "RouteOnDedupResult",
      "Catch": [{"ErrorEquals": ["States.ALL"], "Next": "CaseCreationFailed"}]
    },
    "RouteOnDedupResult": {
      "Type": "Choice",
      "Choices": [
        {"Variable": "$.dedupResult.classification", "StringEquals": "DUPLICATE", "Next": "LogDuplicateAndStop"},
        {"Variable": "$.dedupResult.classification", "StringEquals": "MERGED", "Next": "GatherEvidence"},
        {"Variable": "$.dedupResult.classification", "StringEquals": "NEW_CASE", "Next": "GatherEvidence"}
      ],
      "Default": "CaseCreationFailed"
    },
    "LogDuplicateAndStop": {
      "Type": "Task", "Resource": "${duplicate_logger_arn}",
      "End": true
    },
    "GatherEvidence": {
      "Type": "Parallel",
      "Branches": [
        {"StartAt": "FetchCustomer", "States": {"FetchCustomer": {
          "Type": "Task", "Resource": "${evidence_customer_arn}",
          "TimeoutSeconds": 2,
          "Catch": [{"ErrorEquals": ["States.ALL"], "ResultPath": "$.error", "Next": "CustomerFailed"}],
          "End": true},
          "CustomerFailed": {"Type": "Pass",
            "Parameters": {"source": "CUSTOMER", "status": "FAILED", "evidence_id.$": "$.evidenceId", "error.$": "$.error"},
            "End": true}}},
        {"StartAt": "FetchTransaction", "States": {"FetchTransaction": {
          "Type": "Task", "Resource": "${evidence_transaction_arn}",
          "TimeoutSeconds": 2,
          "Catch": [{"ErrorEquals": ["States.ALL"], "ResultPath": "$.error", "Next": "TransactionFailed"}],
          "End": true},
          "TransactionFailed": {"Type": "Pass",
            "Parameters": {"source": "TRANSACTION", "status": "FAILED", "evidence_id.$": "$.evidenceId", "error.$": "$.error"},
            "End": true}}},
        {"StartAt": "FetchBeneficiary", "States": {"FetchBeneficiary": {
          "Type": "Task", "Resource": "${evidence_beneficiary_arn}",
          "TimeoutSeconds": 2,
          "Catch": [{"ErrorEquals": ["States.ALL"], "ResultPath": "$.error", "Next": "BeneficiaryFailed"}],
          "End": true},
          "BeneficiaryFailed": {"Type": "Pass",
            "Parameters": {"source": "BENEFICIARY", "status": "FAILED", "evidence_id.$": "$.evidenceId", "error.$": "$.error"},
            "End": true}}},
        {"StartAt": "FetchDevice", "States": {"FetchDevice": {
          "Type": "Task", "Resource": "${evidence_device_arn}",
          "TimeoutSeconds": 2,
          "Catch": [{"ErrorEquals": ["States.ALL"], "ResultPath": "$.error", "Next": "DeviceFailed"}],
          "End": true},
          "DeviceFailed": {"Type": "Pass",
            "Parameters": {"source": "DEVICE", "status": "FAILED", "evidence_id.$": "$.evidenceId", "error.$": "$.error"},
            "End": true}}},
        {"StartAt": "FetchKYC", "States": {"FetchKYC": {
          "Type": "Task", "Resource": "${evidence_kyc_arn}",
          "TimeoutSeconds": 2,
          "Catch": [{"ErrorEquals": ["States.ALL"], "ResultPath": "$.error", "Next": "KYCFailed"}],
          "End": true},
          "KYCFailed": {"Type": "Pass",
            "Parameters": {"source": "KYC", "status": "FAILED", "evidence_id.$": "$.evidenceId", "error.$": "$.error"},
            "End": true}}},
        {"StartAt": "FetchSAFPS", "States": {"FetchSAFPS": {
          "Type": "Task", "Resource": "${evidence_safps_arn}",
          "TimeoutSeconds": 2,
          "Catch": [{"ErrorEquals": ["States.ALL"], "ResultPath": "$.error", "Next": "SAFPSFailed"}],
          "End": true},
          "SAFPSFailed": {"Type": "Pass",
            "Parameters": {"source": "SAFPS", "status": "FAILED", "evidence_id.$": "$.evidenceId", "error.$": "$.error"},
            "End": true}}}
      ],
      "Next": "FreezeSnapshot"
    },
    "FreezeSnapshot": {
      "Type": "Task", "Resource": "${snapshot_writer_arn}",
      "Next": "ComputeIndicators"
    },
    "ComputeIndicators": {
      "Type": "Task", "Resource": "${indicator_engine_arn}",
      "Next": "ResolveEntityGraph"
    },
    "ResolveEntityGraph": {
      "Type": "Task", "Resource": "${entity_graph_arn}",
      "Next": "ClassifyScenario"
    },
    "ClassifyScenario": {
      "Type": "Task", "Resource": "${scenario_classifier_arn}",
      "Next": "GenerateNarrative"
    },
    "GenerateNarrative": {
      "Type": "Task", "Resource": "${llm_narrative_arn}",
      "TimeoutSeconds": 10,
      "Catch": [{"ErrorEquals": ["States.ALL"], "ResultPath": "$.narrativeError", "Next": "ValidateNarrative"}],
      "Next": "ValidateNarrative"
    },
    "ValidateNarrative": {
      "Type": "Task", "Resource": "${narrative_validator_arn}",
      "Next": "PrioritiseAndStoreCase"
    },
    "PrioritiseAndStoreCase": {
      "Type": "Task", "Resource": "${case_writer_arn}",
      "End": true
    },
    "CaseCreationFailed": {
      "Type": "Task", "Resource": "${alert_dlq_writer_arn}",
      "End": true
    }
  }
}
