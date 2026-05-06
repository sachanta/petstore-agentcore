# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import logging
import os

import boto3
from bedrock_agentcore.runtime import BedrockAgentCoreApp
import pet_store_agent

logger = logging.getLogger(__name__)
app = BedrockAgentCoreApp()


def _check_guardrail(prompt: str) -> str | None:
    """
    Apply the Bedrock Guardrail to the user INPUT only.
    Returns None if the input is allowed; returns a JSON Reject string if blocked.
    Applying the guardrail here (not on every LLM step) avoids false-positive
    blocks on the agent's own intermediate reasoning outputs.
    """
    guardrail_id      = os.environ.get("GUARDRAIL_ID")
    guardrail_version = os.environ.get("GUARDRAIL_VERSION", "1")
    if not guardrail_id:
        return None

    region  = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    bedrock = boto3.client("bedrock-runtime", region_name=region)

    try:
        resp = bedrock.apply_guardrail(
            guardrailIdentifier=guardrail_id,
            guardrailVersion=str(guardrail_version),
            source="INPUT",
            content=[{"text": {"text": prompt}}],
        )
        if resp.get("action") == "GUARDRAIL_INTERVENED":
            logger.info("Guardrail blocked input.")
            return json.dumps({
                "status":  "Reject",
                "message": "Sorry! We can't accept your request. What else do you need?",
            })
    except Exception as e:
        logger.warning("Guardrail check failed (proceeding without block): %s", e)

    return None


def _fetch_inventory(product_code: str) -> dict | None:
    """Fetch inventory record for a product from the Lambda backend."""
    try:
        import boto3
        lambda_client = boto3.client("lambda", region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
        payload = {"function": "getInventory", "parameters": [{"name": "product_code", "value": product_code}]}
        resp = lambda_client.invoke(
            FunctionName=os.environ.get("SYSTEM_FUNCTION_1_NAME", ""),
            Payload=json.dumps(payload),
        )
        outer = json.loads(resp["Payload"].read())
        return json.loads(outer["response"]["functionResponse"]["responseBody"]["TEXT"]["body"])
    except Exception as e:
        logger.warning("Could not fetch inventory for %s: %s", product_code, e)
        return None


def _apply_business_rules(response_str: str) -> str:
    """
    Deterministically recalculate numeric business rules from the items list
    returned by the LLM, overwriting any incorrect values the LLM may have computed.

    Rules applied:
    - bundleDiscount: 0.10 on each additional unit of the same product (2nd unit onward)
    - item.total = price × quantity × (1 - bundleDiscount for additional units)
    - subtotal = sum(item.total)
    - additionalDiscount: 0.15 when subtotal > $300 (else 0)
    - shippingCost: free when subtotal >= $75; $19.95 for ≥3 total units; else $14.95
    - total = subtotal × (1 - additionalDiscount) + shippingCost
    - replenishInventory: true when post-order qty ≤ reorder_level (fetched from Lambda)
    """
    try:
        data = json.loads(response_str)
        if not isinstance(data, dict):
            data = json.loads(data)
    except Exception:
        return response_str

    if data.get("status") != "Accept":
        return json.dumps(data)

    items = data.get("items")
    if not items:
        return json.dumps(data)

    # Track quantities per product to compute bundle discounts and replenishment
    qty_by_product: dict[str, int] = {}
    for item in items:
        pid = item.get("productId", "")
        qty_by_product[pid] = qty_by_product.get(pid, 0) + int(item.get("quantity", 1))

    # Recalculate bundle discounts and item totals
    qty_seen: dict[str, int] = {}
    total_units = 0
    for item in items:
        pid = item.get("productId", "")
        price = float(item.get("price", 0))
        qty = int(item.get("quantity", 1))
        total_units += qty

        seen_before = qty_seen.get(pid, 0)
        full_price_units = max(0, 1 - seen_before)
        discounted_units = qty - full_price_units

        if discounted_units > 0:
            item["bundleDiscount"] = 0.10
            item_total = (full_price_units * price) + (discounted_units * price * 0.90)
        else:
            item["bundleDiscount"] = 0
            item_total = price * qty

        item["total"] = round(item_total, 2)
        qty_seen[pid] = seen_before + qty

    subtotal = round(sum(i["total"] for i in items), 2)
    data["subtotal"] = subtotal

    # Order discount
    additional_discount = 0.15 if subtotal > 300 else 0
    data["additionalDiscount"] = additional_discount

    # Shipping
    if subtotal >= 75:
        shipping = 0.0
    elif total_units >= 3:
        shipping = 19.95
    else:
        shipping = 14.95
    data["shippingCost"] = shipping

    # Final total
    data["total"] = round(subtotal * (1 - additional_discount) + shipping, 2)

    # Replenishment flags — deterministic: fetch live inventory and compare
    for item in items:
        pid = item.get("productId", "")
        ordered_qty = qty_by_product.get(pid, 0)
        inv = _fetch_inventory(pid)
        if inv:
            remaining = inv.get("quantity", 0) - ordered_qty
            item["replenishInventory"] = remaining <= inv.get("reorder_level", 0)

    return json.dumps(data)


@app.entrypoint
def handler(payload):
    """AgentCore handler function"""
    prompt = payload.get("prompt", "A new user is asking about the price of Doggy Delights?")

    blocked = _check_guardrail(prompt)
    if blocked:
        return blocked

    response = pet_store_agent.process_request(prompt)
    return _apply_business_rules(response)


if __name__ == "__main__":
    app.run()