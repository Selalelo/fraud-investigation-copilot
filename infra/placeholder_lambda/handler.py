"""Placeholder handler -- proves the infrastructure (Step Functions -> Lambda -> IAM -> logging)
end to end. Real handler logic is a port of src/fraud_copilot/*.py, out of scope for this
Terraform pass (see README.md: 'This proves the infrastructure, not a full Lambda port')."""
import json
import os


def handler(event, context):
    print(json.dumps({"function": os.environ.get("FUNCTION_NAME", "unknown"), "event": event}))
    return {"status": "not_implemented", "function": os.environ.get("FUNCTION_NAME", "unknown")}
