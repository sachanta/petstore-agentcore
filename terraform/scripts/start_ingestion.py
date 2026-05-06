#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#
# Starts a Bedrock Knowledge Base ingestion job and polls until complete.
# Called by Terraform null_resource provisioner after S3 data source creation.
# Exit code non-zero = Terraform error.
#
# Usage:
#   python3 start_ingestion.py \
#     --knowledge-base-id <kb-id> \
#     --data-source-id <ds-id> \
#     --region us-east-1

import argparse
import logging
import sys
import time

import boto3

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

POLL_INTERVAL = 15
TIMEOUT_MINS = 20


def start_ingestion(client, kb_id: str, ds_id: str) -> str:
    log.info("Starting ingestion job for KB=%s DS=%s", kb_id, ds_id)
    resp = client.start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id)
    job_id = resp["ingestionJob"]["ingestionJobId"]
    log.info("Ingestion job started: %s", job_id)
    return job_id


def poll_ingestion(client, kb_id: str, ds_id: str, job_id: str) -> None:
    deadline = time.time() + TIMEOUT_MINS * 60
    while time.time() < deadline:
        resp = client.get_ingestion_job(
            knowledgeBaseId=kb_id, dataSourceId=ds_id, ingestionJobId=job_id
        )
        job = resp["ingestionJob"]
        status = job["status"]
        stats = job.get("statistics", {})
        log.info(
            "Status: %s | indexed=%s failed=%s deleted=%s",
            status,
            stats.get("numberOfDocumentsIndexed", "?"),
            stats.get("numberOfDocumentsFailed", "?"),
            stats.get("numberOfDocumentsDeleted", "?"),
        )

        if status == "COMPLETE":
            log.info("Ingestion complete.")
            if stats.get("numberOfDocumentsFailed", 0) > 0:
                log.warning(
                    "%d documents failed to index.", stats["numberOfDocumentsFailed"]
                )
            return
        if status in ("FAILED", "STOPPED"):
            failures = job.get("failureReasons", [])
            log.error("Ingestion job failed. Reasons: %s", failures)
            sys.exit(1)

        time.sleep(POLL_INTERVAL)

    log.error("Timed out waiting for ingestion job after %d minutes.", TIMEOUT_MINS)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Start and monitor a Bedrock KB ingestion job")
    parser.add_argument("--knowledge-base-id", required=True)
    parser.add_argument("--data-source-id", required=True)
    parser.add_argument("--region", required=True)
    args = parser.parse_args()

    client = boto3.client("bedrock-agent", region_name=args.region)

    job_id = start_ingestion(client, args.knowledge_base_id, args.data_source_id)
    poll_ingestion(client, args.knowledge_base_id, args.data_source_id, job_id)


if __name__ == "__main__":
    main()
