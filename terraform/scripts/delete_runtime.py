#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#
# Deletes the AgentCore Runtime by name, polls until gone.
# Called by the null_resource destroy provisioner.
#
# Usage:
#   python3 delete_runtime.py \
#     --runtime-name LangGraphAgentCoreRuntime \
#     --region us-east-1

import argparse
import logging
import sys
import time

import boto3
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

POLL_INTERVAL = 15   # seconds
TIMEOUT       = 300  # 5 minutes


def find_runtime_id(client, name: str):
    paginator = client.get_paginator("list_agent_runtimes")
    for page in paginator.paginate():
        for rt in page.get("agentRuntimes", []):
            if rt["agentRuntimeName"] == name:
                return rt["agentRuntimeId"]
    return None


def main():
    parser = argparse.ArgumentParser(description="Delete AgentCore Runtime")
    parser.add_argument("--runtime-name", required=True)
    parser.add_argument("--region",       required=True)
    args = parser.parse_args()

    client = boto3.client("bedrock-agentcore-control", region_name=args.region)

    rt_id = find_runtime_id(client, args.runtime_name)
    if not rt_id:
        log.info("Runtime '%s' not found — nothing to delete.", args.runtime_name)
        return

    log.info("Deleting runtime %s (%s)...", args.runtime_name, rt_id)
    try:
        client.delete_agent_runtime(agentRuntimeId=rt_id)
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            log.info("Runtime already deleted.")
            return
        raise

    # Poll until ResourceNotFoundException confirms deletion
    deadline = time.time() + TIMEOUT
    while time.time() < deadline:
        try:
            resp = client.get_agent_runtime(agentRuntimeId=rt_id)
            log.info("Runtime status: %s — waiting...", resp.get("status"))
            time.sleep(POLL_INTERVAL)
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                log.info("Runtime deleted.")
                return
            raise

    log.warning("Timed out waiting for runtime deletion — continuing.")


if __name__ == "__main__":
    main()
