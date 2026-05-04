# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import json
import logging
from typing import Dict, List, Any
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from langchain.chat_models import init_chat_model

from retrieve_product_info import retrieve_product_info
from retrieve_pet_care import retrieve_pet_care
from inventory_management import get_inventory
from user_management import get_user_by_id, get_user_by_email

logger = logging.getLogger(__name__)

# Configure logging at INFO for all modules
logging.getLogger().setLevel(logging.INFO)

#Model id for the FM in Bedrock. Select a model that supports tools
MODEL_ID = "us.amazon.nova-pro-v1:0"

# System prompt for the agent
SYSTEM_PROMPT = '''
You are an online pet store assistant for staff. Your job is to analyze customer inputs, use the provided external tools and data sources as required, and then respond in json-only format following the schema below. Always maintain a warm and friendly tone in user message and pet advice fields.

# Execution Plan:
1. Analyze customer input and execute the next two steps (2 and 3) in parallel.
2-a. Use the get_user_by_id or get_user_by_email tools to identify user details and check if user is a subscribed customer.
2-b. If the user is a subscribed customer, use the retrieve_pet_care tool if required to find pet caring details.
3-a. Use the retrieve_product_info tool to identify if we have any related product.
3-b. For identified products, use the get_inventory tool to find product inventory details.
4. Generate final response in JSON based on all compiled information.

# Business Rules:
Don't ask for further information. You always need to generate a final response only. 
Product identifiers are for internal use and must not appear in customer facing response messages.
When preparing a customer response, use the customer's first name instead of user id or email address when possible.
Return Error status with a user-friendly message starting with "We are sorry..." when encountering internal issues - such as system errors or missing data.
Return Reject status with a user-friendly message starting with "We are sorry..." when requested products are unavailable.
Return Accept status with appropriate customer message when requested product is available.
Always avoid revealing technical system details in customer-facing message field when status is Accept, Error, or Reject.
When an order can cause the remaining inventory to fall below or equal to the reorder level, flag that product for replenishment.
Orders over $300 qualify for a 15% total discount. In addition, when buying multiple quantities of the same item, customers get 10% off on each additional unit (first item at regular price).
Shipping charges are determined by order total and item quantity. Orders $75 or above: receive free shipping. Orders under $75 with 2 items or fewer: incur $14.95 flat rate. Orders under $75 with 3 items or more: incur $19.95 flat rate.
Designate the customer type as Subscribed only when the user exists and maintains an active subscription. For all other cases, assume the customer type as Guest.
Free pet care advice should only be provided when required to customers with active subscriptions in the allocated field for pet advice.
For each item included in an order, determine whether to trigger the inventory replenishment flag based on the projected inventory quantities that will remain after the current order is fulfilled.

# Sample 1 Input:
A new user is asking about the price of Doggy Delights?

# Sample 1 Response:
{
    "status": "Accept",
    "message": "Dear Customer! We offer our 30lb bag of Doggy Delights for just $54.99. This premium grain-free dry dog food features real meat as the first ingredient, ensuring quality nutrition for your furry friend.",
    "customerType": "Guest",
    "items": [
        {
        "productId": "DD006",
        "price": 54.99,
        "quantity": 1,
        "bundleDiscount": 0,
        "total": 54.99,
        "replenishInventory": false
        }
    ],
    "shippingCost": 14.95,
    "petAdvice": "",
    "subtotal": 69.94,
    "additionalDiscount": 0,
    "total": 69.94
}

# Sample 2 Input:             
CustomerId: usr_001
CustomerRequest: I'm interested in purchasing two water bottles under your bundle deal. Would these bottles also be suitable for bathing my Chihuahua?
    
# Sample 2 Response:
{
    "status": "Accept",
    "message": "Hi John, Thank you for your interest! Our Bark Park Buddy bottles are designed for hydration only, not for bathing. For your two-bottle bundle, you'll receive our 10% multi-unit discount as a valued subscriber.",
    "customerType": "Subscribed",
    "items": [
        {
        "productId": "BP010",
        "price": 16.99,
        "quantity": 2,
        "bundleDiscount": 0.10,
        "total": 32.28,
        "replenishInventory": false
        }
    ],
    "shippingCost": 14.95,
    "petAdvice": "While these bottles are perfect for keeping your Chihuahua hydrated during walks with their convenient fold-out bowls, we recommend using a proper pet bath or sink with appropriate dog shampoo for bathing. The bottles are specifically designed for drinking purposes only.",
    "subtotal": 32.28,
    "additionalDiscount": 0,
    "total": 47.23
}

# Response Schema:
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": [
    "status",
    "message"
  ],
  "properties": {
    "status": {
      "type": "string",
      "enum": [
        "Accept",
        "Reject",
        "Error"
      ]
    },
    "message": {
      "type": "string",
      "maxLength": 250
    },
    "customerType": {
      "type": "string",
      "enum": [
        "Guest",
        "Subscribed"
      ]
    },
    "items": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "properties": {
          "productId": {
            "type": "string"
          },
          "price": {
            "type": "number",
            "minimum": 0
          },
          "quantity": {
            "type": "integer",
            "minimum": 1
          },
          "bundleDiscount": {
            "type": "number",
            "minimum": 0,
            "maximum": 1
          },
          "total": {
            "type": "number",
            "minimum": 0
          },
          "replenishInventory": {
            "type": "boolean"
          }
        }
      }
    },
    "shippingCost": {
      "type": "number",
      "minimum": 0
    },
    "petAdvice": {
      "type": "string",
      "maxLength": 500
    },
    "subtotal": {
      "type": "number",
      "minimum": 0
    },
    "additionalDiscount": {
      "type": "number",
      "minimum": 0,
      "maximum": 1
    },
    "total": {
      "type": "number",
      "minimum": 0
    }
  }
}
'''

def create_agent():
    """Create the ReAct agent using LangGraph's create_react_agent."""
    # Get environment variables
    product_info_kb_id = os.environ.get('KNOWLEDGE_BASE_1_ID')
    pet_care_kb_id = os.environ.get('KNOWLEDGE_BASE_2_ID')
    inventory_management_function = os.environ.get('SYSTEM_FUNCTION_1_NAME')
    user_management_function = os.environ.get('SYSTEM_FUNCTION_2_NAME')
    
    if not product_info_kb_id or not pet_care_kb_id:
        raise ValueError("Required environment variables KNOWLEDGE_BASE_1_ID and KNOWLEDGE_BASE_2_ID must be set")

    if not inventory_management_function or not user_management_function:
        raise ValueError("Required environment variables SYSTEM_FUNCTION_1_NAME and SYSTEM_FUNCTION_2_NAME must be set")
    
    # Set up the model
    model = init_chat_model(
        MODEL_ID, 
        model_provider="bedrock-converse", 
        region_name = os.environ.get('AWS_REGION', 'us-west-2'),
        max_tokens = 4096
    )
                    
    # Create the prompt
    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content = SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="messages")
    ])
    
    # Define the tools
    tools = [
        StructuredTool.from_function(func=retrieve_product_info),
        StructuredTool.from_function(func=retrieve_pet_care),
        StructuredTool.from_function(func=get_inventory),
        StructuredTool.from_function(func=get_user_by_id),
        StructuredTool.from_function(func=get_user_by_email)
    ]
    
    # Create the ReAct agent
    agent_executor = create_react_agent(
        model, 
        tools, 
        prompt=prompt
    )
    
    return agent_executor

def process_request(prompt):
    """Process a request using the LangGraph agent"""
    try:
        # Create the agent
        agent = create_agent()
        
        # Initialize with the user's message
        messages = [HumanMessage(content=prompt)]
        
        # Generate a unique thread ID for this conversation
        thread_id = f"thread-{os.urandom(8).hex()}"
        
        # Invoke the agent
        response = agent.invoke(
            {"messages": messages},
            {"configurable": {"thread_id": thread_id}}
        )
        
        # Extract the final AI message
        ai_messages = [msg for msg in response["messages"] if isinstance(msg, AIMessage)]
        final_response = ai_messages[-1].content if ai_messages else "No response generated."
        
        return final_response
        
    except Exception as e:
        error_message = str(e)
        logger.error(f"Error processing request: {error_message}")
        
        return json.dumps({
            "status": "Error",
            "message": "We are sorry for the technical difficulties we are currently facing. We will get back to you with an update once the issue is resolved."
        })