#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#
# Creates or destroys the two AOSS vector indices needed by the pet store KBs.
# Called by Terraform null_resource provisioner — exit code non-zero = Terraform error.
#
# Usage:
#   python3 create_vector_indices.py --collection-name clashofagents \
#       --region us-east-1 --endpoint https://<id>.us-east-1.aoss.amazonaws.com
#   python3 create_vector_indices.py ... --destroy

import argparse
import json
import logging
import sys
import time

import boto3
import requests
from requests_aws4auth import AWS4Auth

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

PRODUCT_INFO_INDEX = "product_info_index"
PET_CARE_INDEX = "pet_care_index"

# 1024 dims = Titan Embed Text v2 output size
INDEX_BODY = {
    "settings": {
        "index.knn": True
    },
    "mappings": {
        "properties": {
            "vector": {
                "type": "knn_vector",
                "dimension": 1024,
                "method": {
                    "name": "hnsw",
                    "space_type": "l2",
                    "engine": "faiss"
                }
            },
            "text": {"type": "text"},
            "metadata": {"type": "text"}
        }
    }
}


def get_awsauth(region: str) -> AWS4Auth:
    session = boto3.Session()
    credentials = session.get_credentials().get_frozen_credentials()
    return AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        region,
        "aoss",
        session_token=credentials.token,
    )


def wait_for_collection_active(collection_name: str, region: str, timeout_mins: int = 10) -> str:
    """Poll until the collection is ACTIVE. Returns the collection endpoint."""
    client = boto3.client("opensearchserverless", region_name=region)
    deadline = time.time() + timeout_mins * 60
    log.info("Waiting for collection '%s' to become ACTIVE...", collection_name)

    while time.time() < deadline:
        resp = client.batch_get_collection(names=[collection_name])
        details = resp.get("collectionDetails", [])
        if not details:
            log.info("Collection not found yet, retrying in 15s...")
            time.sleep(15)
            continue

        status = details[0].get("status")
        endpoint = details[0].get("collectionEndpoint", "")
        log.info("Collection status: %s", status)

        if status == "ACTIVE":
            log.info("Collection is ACTIVE. Endpoint: %s", endpoint)
            return endpoint
        if status in ("FAILED", "DELETING", "DELETED"):
            log.error("Collection entered terminal status: %s", status)
            sys.exit(1)

        time.sleep(15)

    log.error("Timed out waiting for collection to become ACTIVE after %d minutes.", timeout_mins)
    sys.exit(1)


def create_index(endpoint: str, index_name: str, awsauth: AWS4Auth) -> None:
    url = f"{endpoint}/{index_name}"
    headers = {"Content-Type": "application/json"}

    # Index may already exist — check first
    check = requests.head(url, auth=awsauth)
    if check.status_code == 200:
        log.info("Index '%s' already exists, skipping creation.", index_name)
        return

    log.info("Creating index '%s'...", index_name)
    resp = requests.put(url, auth=awsauth, json=INDEX_BODY, headers=headers)
    log.info("Response %d: %s", resp.status_code, resp.text)
    resp.raise_for_status()
    log.info("Index '%s' created successfully.", index_name)


def delete_index(endpoint: str, index_name: str, awsauth: AWS4Auth) -> None:
    url = f"{endpoint}/{index_name}"
    log.info("Deleting index '%s'...", index_name)
    resp = requests.delete(url, auth=awsauth)
    if resp.status_code == 404:
        log.info("Index '%s' not found (already deleted).", index_name)
        return
    log.info("Response %d: %s", resp.status_code, resp.text)
    resp.raise_for_status()
    log.info("Index '%s' deleted.", index_name)


def main():
    parser = argparse.ArgumentParser(description="Manage AOSS vector indices for pet store KBs")
    parser.add_argument("--collection-name", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--endpoint", required=True, help="AOSS collection HTTPS endpoint")
    parser.add_argument("--destroy", action="store_true", help="Delete indices instead of creating")
    args = parser.parse_args()

    # Even with endpoint provided, confirm collection is ACTIVE before proceeding
    if not args.destroy:
        endpoint = wait_for_collection_active(args.collection_name, args.region)
    else:
        endpoint = args.endpoint

    awsauth = get_awsauth(args.region)

    if args.destroy:
        delete_index(endpoint, PRODUCT_INFO_INDEX, awsauth)
        delete_index(endpoint, PET_CARE_INDEX, awsauth)
        log.info("Destroy complete.")
    else:
        create_index(endpoint, PRODUCT_INFO_INDEX, awsauth)
        create_index(endpoint, PET_CARE_INDEX, awsauth)
        log.info("All indices created successfully.")


if __name__ == "__main__":
    main()
