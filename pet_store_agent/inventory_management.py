# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import json
import boto3
import logging

logger = logging.getLogger(__name__)

def get_inventory(product_code: str = None) -> str:
    """
    Get inventory information for products.
    
    Args:
        product_code: Optional product code. Without product_code: Returns list of all products with their inventory levels. With product_code: Returns inventory details for specific product.
    
    Returns:
        JSON string with inventory information
        
    Sample Input Request:
    {
        "function": "getInventory",
        "parameters": [
            {
                "name": "product_code",
                "value": "CM001"
            }
        ]
    }

    Sample Response Body:
    {
        "product_code": "CM001",
        "name": "Meow Munchies",
        "quantity": 150,
        "last_updated": "ISO-8601 date",
        "status": "in_stock|low_stock|out_of_stock",
        "reorder_level": 50
    }
    """
    logger.info(f"get_inventory called with input: product_code={product_code}")
    
    lambda_client = boto3.client('lambda')
    
    payload = {
        "function": "getInventory",
        "parameters": []
    }
    
    if product_code:
        payload["parameters"].append({
            "name": "product_code",
            "value": product_code
        })
    
    try:
        response = lambda_client.invoke(
            FunctionName=os.environ.get('SYSTEM_FUNCTION_1_NAME'),
            Payload=json.dumps(payload)
        )
        
        lambda_response = json.loads(response['Payload'].read())
        # Extract the actual data from the nested response structure
        actual_data = json.loads(lambda_response['response']['functionResponse']['responseBody']['TEXT']['body'])
        
        result = json.dumps(actual_data)
        logger.info(f"get_inventory returning result: {result}")
        return result
    except Exception as e:
        logger.error(f"get_inventory() error: {str(e)}")
        
        result = f"Failed to get inventory: {str(e)}"
        logger.info(f"get_inventory returning result: {result}")
        return result