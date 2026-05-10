# ─────────────────────────────────────────────────────────────
# Makefile — Terraform wrapper that auto-loads terraform/.env
#
# Usage:
#   make apply      Full deploy
#   make destroy    Tear everything down
#   make plan       Preview changes without applying
#   make runtime    Redeploy only the AgentCore Runtime (fast, ~30s)
#   make output     Print all terraform outputs
#
# First-time setup:
#   cp .env.example .env
#   # edit .env and fill in your Arize API key
# ─────────────────────────────────────────────────────────────

ENV_FILE := $(CURDIR)/.env

# Load .env if it exists — exports all TF_VAR_* into the environment
ifneq (,$(wildcard $(ENV_FILE)))
  include $(ENV_FILE)
  export $(shell sed 's/=.*//' $(ENV_FILE) | grep -v '^#' | grep -v '^$$')
endif

.PHONY: apply destroy plan runtime output check-env

check-env:
	@if [ ! -f "$(ENV_FILE)" ]; then \
		echo "ERROR: terraform/.env not found."; \
		echo "  cp terraform/.env.example terraform/.env"; \
		echo "  then fill in your Arize API key."; \
		exit 1; \
	fi

apply: check-env
	terraform apply -auto-approve

destroy: check-env
	terraform destroy -auto-approve

plan: check-env
	terraform plan

runtime: check-env
	terraform apply -auto-approve -target=module.agent_runtime.null_resource.agent_runtime

output:
	terraform output
