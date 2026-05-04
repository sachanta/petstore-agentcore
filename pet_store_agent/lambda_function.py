# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import pet_store_agent

def handler(event, context):
    """Lambda handler function"""
    prompt = event.get('prompt', 'A new user is asking about the price of Doggy Delights?')
    return pet_store_agent.process_request(prompt)