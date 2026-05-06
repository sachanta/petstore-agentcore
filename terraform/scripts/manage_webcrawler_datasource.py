#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#
# Creates (or destroys) the web crawler data source for PetCaringKnowledge KB.
# There is no native Terraform resource for Bedrock WEB data sources.
# Called by Terraform null_resource provisioner.
#
# On create: creates data source, starts ingestion (fire-and-forget — web crawl
#            can take many minutes; we don't block apply waiting for it).
# On destroy: finds the data source by name, deletes it.
#
# Usage:
#   python3 manage_webcrawler_datasource.py \
#     --knowledge-base-id <kb-id> --region us-east-1
#   python3 manage_webcrawler_datasource.py \
#     --knowledge-base-id <kb-id> --region us-east-1 --destroy

import argparse
import logging
import sys
import time

import boto3
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATA_SOURCE_NAME = "WebCrawlerDataSource"

SEED_URLS = [
    "https://en.wikipedia.org/wiki/Cat_food",
    "https://en.wikipedia.org/wiki/Cat_play_and_toys",
    "https://en.wikipedia.org/wiki/Dog_food",
    "https://en.wikipedia.org/wiki/Dog_grooming",
]


def create_datasource(client, kb_id: str) -> str:
    # Check if already exists (idempotent)
    ds_id = find_datasource(client, kb_id)
    if ds_id:
        log.info("Web crawler data source already exists: %s", ds_id)
        return ds_id

    log.info("Creating web crawler data source for KB %s...", kb_id)
    resp = client.create_data_source(
        knowledgeBaseId=kb_id,
        name=DATA_SOURCE_NAME,
        dataSourceConfiguration={
            "type": "WEB",
            "webConfiguration": {
                "sourceConfiguration": {
                    "urlConfiguration": {
                        "seedUrls": [{"url": u} for u in SEED_URLS]
                    }
                },
                "crawlerConfiguration": {
                    "inclusionFilters": [".*"]
                },
            },
        },
    )
    ds_id = resp["dataSource"]["dataSourceId"]
    log.info("Created data source: %s", ds_id)
    return ds_id


def start_ingestion(client, kb_id: str, ds_id: str) -> None:
    log.info("Starting web crawler ingestion job (fire-and-forget)...")
    try:
        resp = client.start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id)
        job_id = resp["ingestionJob"]["ingestionJobId"]
        log.info("Ingestion job started: %s (web crawl runs in background)", job_id)
    except ClientError as e:
        # ConflictException: ingestion already running — that's fine
        if e.response["Error"]["Code"] == "ConflictException":
            log.info("Ingestion job already running.")
        else:
            raise


def find_datasource(client, kb_id: str) -> str | None:
    """Return the data source ID for WebCrawlerDataSource, or None."""
    paginator = client.get_paginator("list_data_sources")
    for page in paginator.paginate(knowledgeBaseId=kb_id):
        for ds in page.get("dataSourceSummaries", []):
            if ds["name"] == DATA_SOURCE_NAME:
                return ds["dataSourceId"]
    return None


def stop_running_ingestion_jobs(client, kb_id: str) -> None:
    """Stop any STARTING or IN_PROGRESS ingestion jobs on this KB.

    Bedrock rejects KB deletion while an ingestion job is running.
    This must be called before deleting the KB or its data sources.
    """
    log.info("Checking for running ingestion jobs on KB %s...", kb_id)
    paginator = client.get_paginator("list_ingestion_jobs")
    # list_ingestion_jobs requires a dataSourceId; we must enumerate data sources first
    ds_paginator = client.get_paginator("list_data_sources")
    for ds_page in ds_paginator.paginate(knowledgeBaseId=kb_id):
        for ds in ds_page.get("dataSourceSummaries", []):
            ds_id = ds["dataSourceId"]
            for page in paginator.paginate(knowledgeBaseId=kb_id, dataSourceId=ds_id):
                for job in page.get("ingestionJobSummaries", []):
                    if job["status"] in ("STARTING", "IN_PROGRESS"):
                        job_id = job["ingestionJobId"]
                        log.info("Stopping ingestion job %s (status=%s)...", job_id, job["status"])
                        try:
                            client.stop_ingestion_job(
                                knowledgeBaseId=kb_id,
                                dataSourceId=ds_id,
                                ingestionJobId=job_id,
                            )
                        except ClientError as e:
                            log.warning("Could not stop ingestion job %s: %s", job_id, e)

    # Wait for all jobs to reach a terminal state
    deadline = time.time() + 120
    while time.time() < deadline:
        any_running = False
        for ds_page in client.get_paginator("list_data_sources").paginate(knowledgeBaseId=kb_id):
            for ds in ds_page.get("dataSourceSummaries", []):
                ds_id = ds["dataSourceId"]
                for page in paginator.paginate(knowledgeBaseId=kb_id, dataSourceId=ds_id):
                    for job in page.get("ingestionJobSummaries", []):
                        if job["status"] in ("STARTING", "IN_PROGRESS"):
                            any_running = True
        if not any_running:
            log.info("All ingestion jobs stopped.")
            return
        log.info("Waiting for ingestion jobs to stop...")
        time.sleep(10)

    log.warning("Timed out waiting for ingestion jobs to stop — continuing anyway.")


def delete_datasource(client, kb_id: str) -> None:
    stop_running_ingestion_jobs(client, kb_id)

    ds_id = find_datasource(client, kb_id)
    if not ds_id:
        log.info("Web crawler data source not found — nothing to delete.")
        return

    log.info("Deleting web crawler data source %s...", ds_id)
    try:
        client.delete_data_source(knowledgeBaseId=kb_id, dataSourceId=ds_id)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("ResourceNotFoundException", "ValidationException"):
            log.info("Data source already deleted.")
            return
        raise

    # Poll until gone
    deadline = time.time() + 120
    while time.time() < deadline:
        remaining = find_datasource(client, kb_id)
        if not remaining:
            log.info("Data source deleted.")
            return
        log.info("Waiting for data source deletion...")
        time.sleep(10)

    log.warning("Timed out waiting for data source deletion — continuing anyway.")


def main():
    parser = argparse.ArgumentParser(description="Manage web crawler data source for PetCaringKnowledge KB")
    parser.add_argument("--knowledge-base-id", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--destroy", action="store_true", help="Delete the data source instead of creating")
    args = parser.parse_args()

    client = boto3.client("bedrock-agent", region_name=args.region)

    if args.destroy:
        delete_datasource(client, args.knowledge_base_id)
        log.info("Destroy complete.")
    else:
        ds_id = create_datasource(client, args.knowledge_base_id)
        start_ingestion(client, args.knowledge_base_id, ds_id)
        log.info("Create complete.")


if __name__ == "__main__":
    main()
