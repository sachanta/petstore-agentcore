# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#
# Inventory Lambda — simulates a pet store inventory system.
# Called by the agent tool inventory_management.get_inventory().
#
# Request format:
#   { "function": "getInventory",
#     "parameters": [{"name": "product_code", "value": "DD006"}] }
#
# Response format (Bedrock agent function response nesting):
#   { "response": { "functionResponse": { "responseBody":
#       { "TEXT": { "body": "<json string>" } } } } }

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_LAST_UPDATED = "2026-05-06T00:00:00Z"

# Full inventory — status is computed dynamically from quantity vs reorder_level.
_PRODUCTS = [
    {"product_code": "DD006", "name": "Doggy Delights",              "quantity": 150, "reorder_level": 50},
    {"product_code": "DD007", "name": "PuppyPower Bites",            "quantity":  45, "reorder_level": 30},
    {"product_code": "DD008", "name": "Senior Serenity Blend",       "quantity":  80, "reorder_level": 25},
    {"product_code": "DD009", "name": "Hearty Stew Wet Dog Food",    "quantity": 200, "reorder_level": 40},
    {"product_code": "DD010", "name": "Mega Feast Bundle Pack",      "quantity":  12, "reorder_level": 10},
    {"product_code": "CM001", "name": "Meow Munchies",               "quantity": 120, "reorder_level": 40},
    {"product_code": "CM002", "name": "Kitten Kickstart",            "quantity":  60, "reorder_level": 20},
    {"product_code": "CM003", "name": "Purrfect Pate Wet Cat Food",  "quantity": 180, "reorder_level": 50},
    {"product_code": "CM004", "name": "Senior Whiskers Formula",     "quantity":  35, "reorder_level": 20},
    {"product_code": "CM005", "name": "Indoor Calm Blend",           "quantity":  90, "reorder_level": 30},
    {"product_code": "BP010", "name": "Bark Park Buddy",             "quantity":  55, "reorder_level": 20},
    {"product_code": "BP011", "name": "ToughChew Rope Toy Set",      "quantity":  75, "reorder_level": 25},
    {"product_code": "BP012", "name": "OrthoRest Dog Bed",           "quantity":   8, "reorder_level": 10},
    {"product_code": "BP013", "name": "ProTrainer Adjustable Harness","quantity":  40, "reorder_level": 15},
    {"product_code": "BP014", "name": "Deluxe Grooming Kit for Dogs","quantity":  30, "reorder_level": 10},
    {"product_code": "BP015", "name": "SmartFeed Automatic Dog Feeder","quantity":  5, "reorder_level":  8},
    {"product_code": "CA001", "name": "ScratchMaster Deluxe Cat Tree","quantity":  18, "reorder_level": 10},
    {"product_code": "CA002", "name": "PurrZen Interactive Laser Toy","quantity":  65, "reorder_level": 20},
    {"product_code": "CA003", "name": "CleanPaws Self-Cleaning Litter Box","quantity": 22,"reorder_level": 10},
    {"product_code": "CA004", "name": "CozyCave Heated Cat Bed",     "quantity":  40, "reorder_level": 15},
    {"product_code": "CA005", "name": "FountainFlow Cat Water Fountain","quantity": 50,"reorder_level": 20},
    {"product_code": "GR001", "name": "FoamFresh Dog Shampoo",       "quantity": 110, "reorder_level": 30},
    {"product_code": "GR002", "name": "GentleGlow Cat Shampoo",      "quantity":  95, "reorder_level": 30},
    {"product_code": "GR003", "name": "ProShine Deshedding Brush",   "quantity":  70, "reorder_level": 20},
    {"product_code": "GR004", "name": "PawPerfect Nail Grinder",     "quantity":  45, "reorder_level": 15},
    {"product_code": "GR005", "name": "SpaDay Pet Grooming Bundle",  "quantity":  15, "reorder_level": 10},
    {"product_code": "TS001", "name": "Chicken Crunch Dog Treats",   "quantity": 200, "reorder_level": 50},
    {"product_code": "TS002", "name": "Salmon Snap Cat Treats",      "quantity": 180, "reorder_level": 50},
    {"product_code": "TS003", "name": "JointEase Dog Supplement",    "quantity":  60, "reorder_level": 20},
    {"product_code": "TS004", "name": "OmegaShine Cat Supplement",   "quantity":  55, "reorder_level": 20},
    {"product_code": "TS005", "name": "DentalFresh Dental Chews",    "quantity":  90, "reorder_level": 25},
]

# Build a lookup dict for O(1) access by product code
_INVENTORY = {p["product_code"]: p for p in _PRODUCTS}


def _compute_status(product: dict) -> str:
    qty = product["quantity"]
    reorder = product["reorder_level"]
    if qty == 0:
        return "out_of_stock"
    if qty <= reorder:
        return "low_stock"
    return "in_stock"


def _enrich(product: dict) -> dict:
    """Return a copy with computed status and last_updated added."""
    return {
        "product_code":  product["product_code"],
        "name":          product["name"],
        "quantity":      product["quantity"],
        "last_updated":  _LAST_UPDATED,
        "status":        _compute_status(product),
        "reorder_level": product["reorder_level"],
    }


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

    if function_name != "getInventory":
        return _make_response({"error": f"Unknown function: {function_name}"})

    product_code = parameters.get("product_code")

    if product_code:
        product = _INVENTORY.get(product_code)
        if not product:
            data = {"error": "Product not found", "product_code": product_code}
        else:
            data = _enrich(product)
    else:
        data = [_enrich(p) for p in _PRODUCTS]

    logger.info("Returning: %s", json.dumps(data))
    return _make_response(data)
