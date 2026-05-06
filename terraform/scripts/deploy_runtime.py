#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#
# Creates or updates the AgentCore Runtime, polls until READY,
# and writes the runtime ID + ARN to a local JSON file for Terraform
# to read back via the local_file data source.
#
# Usage:
#   python3 deploy_runtime.py \
#     --runtime-name LangGraphAgentCoreRuntime \
#     --image-uri <ecr_uri> \
#     --role-arn <arn> \
#     --region us-east-1 \
#     --output-file /path/to/runtime_outputs.json \
#     --env KEY=VAL KEY2=VAL2 ...

import argparse
import json
import logging
import sys
import time

import boto3
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TERMINAL_READY   = "READY"
TERMINAL_FAILED  = "CREATE_FAILED"
POLL_INTERVAL    = 20   # seconds
TIMEOUT          = 900  # 15 minutes


def find_runtime(client, name: str):
    """Return the runtime summary dict if it exists, else None."""
    paginator = client.get_paginator("list_agent_runtimes")
    for page in paginator.paginate():
        for rt in page.get("agentRuntimes", []):
            if rt["agentRuntimeName"] == name:
                return rt
    return None


def build_config(name: str, image_uri: str, role_arn: str, env_vars: dict) -> dict:
    return {
        "agentRuntimeName": name,
        "roleArn":          role_arn,
        "agentRuntimeArtifact": {
            "containerConfiguration": {
                "containerUri": image_uri
            }
        },
        "networkConfiguration": {
            "networkMode": "PUBLIC"
        },
        "lifecycleConfiguration": {
            "maxLifetime": 60
        },
        "environmentVariables": env_vars,
    }


def create_runtime(client, config: dict) -> str:
    log.info("Creating AgentCore Runtime '%s'...", config["agentRuntimeName"])
    resp = client.create_agent_runtime(**config)
    rt_id = resp["agentRuntimeId"]
    log.info("Runtime created: %s", rt_id)
    return rt_id


def update_runtime(client, rt_id: str, config: dict) -> str:
    log.info("Runtime '%s' already exists (%s) — updating...", config["agentRuntimeName"], rt_id)
    update_config = {k: v for k, v in config.items() if k != "agentRuntimeName"}
    client.update_agent_runtime(agentRuntimeId=rt_id, **update_config)
    log.info("Runtime update submitted.")
    return rt_id


def poll_until_ready(client, rt_id: str) -> dict:
    """Poll until READY or FAILED; return the final get-agent-runtime response."""
    deadline = time.time() + TIMEOUT
    while time.time() < deadline:
        resp   = client.get_agent_runtime(agentRuntimeId=rt_id)
        status = resp["status"]
        log.info("Runtime status: %s", status)

        if status == TERMINAL_READY:
            return resp
        if status == TERMINAL_FAILED:
            log.error("Runtime entered CREATE_FAILED state.")
            sys.exit(1)

        log.info("Waiting %ds...", POLL_INTERVAL)
        time.sleep(POLL_INTERVAL)

    log.error("Timed out after %d seconds waiting for READY.", TIMEOUT)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Deploy AgentCore Runtime")
    parser.add_argument("--runtime-name",  required=True)
    parser.add_argument("--image-uri",     required=True)
    parser.add_argument("--role-arn",      required=True)
    parser.add_argument("--region",        required=True)
    parser.add_argument("--output-file",   required=True)
    parser.add_argument("--env",           nargs="*", default=[],
                        metavar="KEY=VALUE",
                        help="Environment variables to inject (KEY=VALUE ...)")
    args = parser.parse_args()

    env_vars = {}
    for kv in args.env:
        k, _, v = kv.partition("=")
        env_vars[k] = v

    client = boto3.client("bedrock-agentcore-control", region_name=args.region)
    config = build_config(args.runtime_name, args.image_uri, args.role_arn, env_vars)

    existing = find_runtime(client, args.runtime_name)
    if existing:
        rt_id = update_runtime(client, existing["agentRuntimeId"], config)
    else:
        rt_id = create_runtime(client, config)

    result = poll_until_ready(client, rt_id)

    output = {
        "agent_runtime_id":  result["agentRuntimeId"],
        "agent_runtime_arn": result["agentRuntimeArn"],
    }

    import os
    os.makedirs(os.path.dirname(args.output_file), exist_ok=True)
    with open(args.output_file, "w") as f:
        json.dump(output, f, indent=2)

    log.info("Runtime READY. ID=%s  ARN=%s", output["agent_runtime_id"], output["agent_runtime_arn"])
    log.info("Outputs written to %s", args.output_file)


if __name__ == "__main__":
    main()
