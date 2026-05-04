# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import json
import boto3
import logging

logger = logging.getLogger(__name__)

def get_user_by_id(user_id: str) -> str:
    """
    Get user information by user ID.
    
    Args:
        user_id: User ID to retrieve information for
    
    Returns:
        JSON string with user information

    Sample Input Request:
    {
        "function": "getUserById",
        "parameters": [
            {
                "name": "user_id",
                "value": "usr_001"
            }
        ]
    }

    Sample Response Body:
    {
        "id": "usr_001",
        "name": "John Doe", 
        "email": "john.doe@virtualpetstore.com",
        "subscription_status": "active|expired",
        "subscription_end_date": "ISO-8601 date",
        "transactions": [
            {
            "id": "txn_001",
            "amount": 29.99,
            "date": "ISO-8601 date",
            "description": "Monthly subscription"
            }
        ]
    }
    """
    logger.info(f"get_user_by_id called with input: user_id={user_id}")
    
    lambda_client = boto3.client('lambda')
    
    payload = {
        "function": "getUserById",
        "parameters": [
            {
                "name": "user_id",
                "value": user_id
            }
        ]
    }
    
    try:
        response = lambda_client.invoke(
            FunctionName=os.environ.get('SYSTEM_FUNCTION_2_NAME'),
            Payload=json.dumps(payload)
        )
        
        lambda_response = json.loads(response['Payload'].read())
        # Extract the actual data from the nested response structure
        actual_data = json.loads(lambda_response['response']['functionResponse']['responseBody']['TEXT']['body'])
        
        result = json.dumps(actual_data)
        logger.info(f"get_user_by_id returning result: {result}")
        return result
    except Exception as e:
        logger.error(f"get_user_by_id() error: {str(e)}")
        
        result = f"Failed to get user by ID: {str(e)}"
        logger.info(f"get_user_by_id returning result: {result}")
        return result

def get_user_by_email(user_email: str) -> str:
    """
    Get user information by email address.
    
    Args:
        user_email: User email to retrieve information for
    
    Returns:
        JSON string with user information
    
    Sample Input Format:
    {
        "function": "getUserByEmail",
        "parameters": [
            {
                "name": "user_email",
                "value": "john.doe@virtualpetstore.com"
            }
        ]
    }
    
    Sample Response Body:
    {
        "id": "usr_001",
        "name": "John Doe", 
        "email": "john.doe@virtualpetstore.com",
        "subscription_status": "active|expired",
        "subscription_end_date": "ISO-8601 date",
        "transactions": [
            {
            "id": "txn_001",
            "amount": 29.99,
            "date": "ISO-8601 date",
            "description": "Monthly subscription"
            }
        ]
    }
    """
    logger.info(f"get_user_by_email called with input: user_email={user_email}")
    
    lambda_client = boto3.client('lambda')
    
    payload = {
        "function": "getUserByEmail",
        "parameters": [
            {
                "name": "user_email",
                "value": user_email
            }
        ]
    }
    
    try:
        response = lambda_client.invoke(
            FunctionName=os.environ.get('SYSTEM_FUNCTION_2_NAME'),
            Payload=json.dumps(payload)
        )
        
        lambda_response = json.loads(response['Payload'].read())
        # Extract the actual data from the nested response structure
        actual_data = json.loads(lambda_response['response']['functionResponse']['responseBody']['TEXT']['body'])
        
        result = json.dumps(actual_data)
        logger.info(f"get_user_by_email returning result: {result}")
        return result
    except Exception as e:
        logger.error(f"get_user_by_email() error: {str(e)}")
        
        result = f"Failed to get user by email: {str(e)}"
        logger.info(f"get_user_by_email returning result: {result}")
        return result