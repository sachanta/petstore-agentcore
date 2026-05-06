# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#
# User Management Lambda — simulates a pet store CRM system.
# Called by the agent tools user_management.get_user_by_id()
# and user_management.get_user_by_email().
#
# Request format:
#   { "function": "getUserById"|"getUserByEmail",
#     "parameters": [{"name": "user_id"|"user_email", "value": "..."}] }
#
# Response format (Bedrock agent function response nesting):
#   { "response": { "functionResponse": { "responseBody":
#       { "TEXT": { "body": "<json string>" } } } } }

import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_USERS = [
    {
        "id":    "usr_001",
        "name":  "John Doe",
        "email": "john.doe@virtualpetstore.com",
        "subscription_status":   "active",
        "subscription_end_date": "2027-01-01T00:00:00Z",
        "transactions": [
            {"id": "txn_001", "amount": 29.99, "date": "2026-04-01T00:00:00Z", "description": "Monthly subscription"},
            {"id": "txn_002", "amount": 49.99, "date": "2026-03-15T00:00:00Z", "description": "Doggy Delights purchase"},
            {"id": "txn_003", "amount": 29.99, "date": "2026-03-01T00:00:00Z", "description": "Monthly subscription"},
        ],
    },
    {
        "id":    "usr_002",
        "name":  "Jane Smith",
        "email": "jane.smith@virtualpetstore.com",
        "subscription_status":   "expired",
        "subscription_end_date": "2025-01-01T00:00:00Z",
        "transactions": [
            {"id": "txn_004", "amount": 29.99, "date": "2024-12-01T00:00:00Z", "description": "Monthly subscription"},
            {"id": "txn_005", "amount": 39.99, "date": "2024-11-20T00:00:00Z", "description": "Meow Munchies purchase"},
        ],
    },
    {
        "id":    "usr_003",
        "name":  "Bob Wilson",
        "email": "bob.wilson@virtualpetstore.com",
        "subscription_status":   "active",
        "subscription_end_date": "2027-06-01T00:00:00Z",
        "transactions": [
            {"id": "txn_006", "amount": 29.99, "date": "2026-04-01T00:00:00Z", "description": "Monthly subscription"},
            {"id": "txn_007", "amount": 89.99, "date": "2026-03-10T00:00:00Z", "description": "OrthoRest Dog Bed purchase"},
            {"id": "txn_008", "amount": 29.99, "date": "2026-03-01T00:00:00Z", "description": "Monthly subscription"},
        ],
    },
]

# Lookup indices for O(1) access
_BY_ID    = {u["id"]:    u for u in _USERS}
_BY_EMAIL = {u["email"]: u for u in _USERS}


def _make_response(data) -> dict:
    """Wrap data in Bedrock agent function response nesting."""
    return {
        "response": {
            "functionResponse": {
                "responseBody": {
                    "TEXT": {
                        "body": json.dumps(data)
                    }
                }
            }
        }
    }


def lambda_handler(event, context):
    logger.info("Event: %s", json.dumps(event))

    function_name = event.get("function", "")
    parameters = {p["name"]: p["value"] for p in event.get("parameters", [])}

    if function_name == "getUserById":
        user_id = parameters.get("user_id")
        user = _BY_ID.get(user_id)
        if not user:
            data = {"error": "User not found", "id": user_id}
        else:
            data = user

    elif function_name == "getUserByEmail":
        user_email = parameters.get("user_email")
        user = _BY_EMAIL.get(user_email)
        if not user:
            data = {"error": "User not found", "email": user_email}
        else:
            data = user

    else:
        data = {"error": f"Unknown function: {function_name}"}

    logger.info("Returning: %s", json.dumps(data))
    return _make_response(data)
