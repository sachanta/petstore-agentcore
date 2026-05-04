# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from bedrock_agentcore.runtime import BedrockAgentCoreApp
import pet_store_agent

app = BedrockAgentCoreApp()

@app.entrypoint
def handler(payload):
    """AgentCore handler function"""
    prompt = payload.get('prompt', 'A new user is asking about the price of Doggy Delights?')
    return pet_store_agent.process_request(prompt)

if __name__ == "__main__":
    app.run()