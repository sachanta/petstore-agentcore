#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#
# Polls a CodeBuild build until it reaches a terminal state.
# Prints live phase status updates. Exits non-zero on FAILED/STOPPED.
#
# Usage:
#   python3 poll_codebuild.py --build-id <id> --region us-east-1

import argparse
import logging
import sys
import time

import boto3

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TERMINAL_STATES = {"SUCCEEDED", "FAILED", "STOPPED", "TIMED_OUT", "FAULT"}
POLL_INTERVAL   = 20   # seconds
TIMEOUT         = 1800 # 30 minutes


def poll(client, build_id: str) -> str:
    """Poll until terminal state; return final status string."""
    deadline = time.time() + TIMEOUT
    last_phase = None

    while time.time() < deadline:
        resp   = client.batch_get_builds(ids=[build_id])
        build  = resp["builds"][0]
        status = build["buildStatus"]
        phases = build.get("phases", [])

        # Print current phase when it changes
        current_phase = next(
            (p["phaseType"] for p in phases if p.get("phaseStatus") == "IN_PROGRESS"),
            None,
        )
        if current_phase and current_phase != last_phase:
            log.info("Phase: %s", current_phase)
            last_phase = current_phase

        if status in TERMINAL_STATES:
            log.info("Build finished: %s", status)
            return status

        log.info("Status: %s — waiting %ds...", status, POLL_INTERVAL)
        time.sleep(POLL_INTERVAL)

    log.error("Timed out after %d seconds.", TIMEOUT)
    return "TIMED_OUT"


def main():
    parser = argparse.ArgumentParser(description="Poll CodeBuild build to completion")
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--region",   required=True)
    args = parser.parse_args()

    client = boto3.client("codebuild", region_name=args.region)
    status = poll(client, args.build_id)

    if status != "SUCCEEDED":
        log.error(
            "Build %s. Check CloudWatch logs for details.\n"
            "  aws codebuild batch-get-builds --ids '%s' "
            "--query 'builds[0].logs.{group:groupName,stream:streamName}'",
            status,
            args.build_id,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
