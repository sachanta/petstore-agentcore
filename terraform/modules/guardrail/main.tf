# ─────────────────────────────────────────────────────────────
# Bedrock Guardrail — PetStoreGuardrail
#
# Enforces two rule types:
#   1. Content filters: block harmful input categories (HATE, INSULTS,
#      SEXUAL, VIOLENCE, MISCONDUCT, PROMPT_ATTACK) at HIGH sensitivity.
#      Output filtering is disabled — only inputs are blocked (NONE strength).
#   2. Topic policy: custom "Beyond-specialization-advice" topic blocks
#      questions about birds, fish, and reptiles (outside pet store scope).
#
# Note: the AWS provider ~5.82 schema for aws_bedrock_guardrail has a
# simplified filters_config (type + input_strength + output_strength only).
# CrossRegionConfig and per-filter action/modality fields are not exposed
# in this provider version — they are set by the service to defaults.
# ─────────────────────────────────────────────────────────────

resource "aws_bedrock_guardrail" "petstore" {
  name        = "PetStoreGuardrail"
  description = "Guardrail for virtual pet store agent to ensure compliance with business rules"

  blocked_input_messaging   = jsonencode({ status = "Reject", message = "Sorry! We can't accept your request. What else do you need?" })
  blocked_outputs_messaging = jsonencode({ status = "Reject", message = "Sorry! We can't process this response. Please try again." })

  # ── Content filters ────────────────────────────────────────
  # input_strength HIGH = block at highest sensitivity.
  # output_strength NONE = don't filter agent outputs.
  content_policy_config {
    filters_config {
      type            = "HATE"
      input_strength  = "HIGH"
      output_strength = "NONE"
    }
    filters_config {
      type            = "INSULTS"
      input_strength  = "HIGH"
      output_strength = "NONE"
    }
    filters_config {
      type            = "SEXUAL"
      input_strength  = "HIGH"
      output_strength = "NONE"
    }
    filters_config {
      type            = "VIOLENCE"
      input_strength  = "HIGH"
      output_strength = "NONE"
    }
    filters_config {
      type            = "MISCONDUCT"
      input_strength  = "HIGH"
      output_strength = "NONE"
    }
    filters_config {
      type            = "PROMPT_ATTACK"
      input_strength  = "HIGH"
      output_strength = "NONE"
    }
  }

  # ── Topic policy ───────────────────────────────────────────
  # Natural language definition + few-shot examples teach Bedrock's
  # classifier what falls under this topic. Type = DENY means
  # matched inputs are blocked (returns blocked_input_messaging).
  topic_policy_config {
    topics_config {
      name       = "Beyond-specialization-advice"
      definition = "Beyond-specialization-advice covers the care and keeping of birds, fish, and reptiles."
      type       = "DENY"
      examples = [
        "How do I care for my parrot?",
        "What temperature should I keep my fish tank?",
        "How often should I feed my snake?",
      ]
    }
  }

  tags = {
    Project = var.project_name
    Phase   = "4-guardrail"
  }
}

# ─────────────────────────────────────────────────────────────
# Guardrail Version
#
# An immutable snapshot of the guardrail DRAFT. The agent runtime
# in Phase 7 references this version number, not the DRAFT.
# This means guardrail changes can be tested before updating the agent.
# ─────────────────────────────────────────────────────────────

resource "aws_bedrock_guardrail_version" "v1" {
  guardrail_arn = aws_bedrock_guardrail.petstore.guardrail_arn
  description   = "Version 1 of Pet Store Guardrail"

  lifecycle {
    create_before_destroy = true
  }
}
