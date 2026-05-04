# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Amazon Bedrock Knowledge Base retrieval tool for product information using LangChain.
"""

import os
import boto3
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

def retrieve_product_info(
    text: str, 
    numberOfResults: int = 10, 
    score: float = 0.25
) -> str:
    """
    Retrieves product information from a knowledge base containing product catalog, 
    descriptions, customer advantages, and detailed specifications.
    
    Args:
        text: The query to retrieve relevant product knowledge.
        numberOfResults: The maximum number of results to return. Default is 10.
        score: Minimum relevance score threshold (0.0-1.0). Default is 0.25.
        
    Returns:
        A formatted string containing the retrieved product information.
    """
    kb_id = os.environ.get('KNOWLEDGE_BASE_1_ID')
    region_name = os.environ.get('AWS_REGION', 'us-west-2')
    
    if not kb_id:
        return "Error: PRODUCT_INFO_KB_ID environment variable not set"

    try:
        # Create a new client for each invocation
        bedrock_agent_runtime_client = boto3.client("bedrock-agent-runtime", region_name=region_name)

        # Perform retrieval
        response = bedrock_agent_runtime_client.retrieve(
            retrievalQuery={"text": text},
            knowledgeBaseId=kb_id,
            retrievalConfiguration={
                "vectorSearchConfiguration": {"numberOfResults": numberOfResults},
            },
        )

        # Get and filter results
        all_results = response.get("retrievalResults", [])
        filtered_results = filter_results_by_score(all_results, score)

        # Format results for display
        formatted_results = format_results_for_display(filtered_results)

        # Return results
        return f"Retrieved {len(filtered_results)} product results with score >= {score}:\n{formatted_results}"

    except Exception as e:
        return f"Error retrieving product information: {str(e)}"


def filter_results_by_score(results: List[Dict[str, Any]], min_score: float) -> List[Dict[str, Any]]:
    """Filter results based on minimum score threshold."""
    return [result for result in results if result.get("score", 0.0) >= min_score]


def format_results_for_display(results: List[Dict[str, Any]]) -> str:
    """Format retrieval results for readable display."""
    if not results:
        return "No results found above score threshold."

    formatted = []
    for result in results:
        doc_id = result.get("location", {}).get("customDocumentLocation", {}).get("id", "Unknown")
        score = result.get("score", 0.0)
        formatted.append(f"\nScore: {score:.4f}")
        formatted.append(f"Document ID: {doc_id}")

        content = result.get("content", {})
        if content and isinstance(content.get("text"), str):
            text = content["text"]
            formatted.append(f"Content: {text}\n")

    return "\n".join(formatted)
