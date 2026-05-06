"""
FastAPI proxy — bridges the Vite frontend to the AWS AgentCore Runtime.
Credentials come from the EC2 instance role automatically via boto3.
"""

import json
import logging
import os
import re

from dotenv import load_dotenv
load_dotenv()

import boto3
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

RUNTIME_ARN = os.environ.get("RUNTIME_ARN", "")
REGION      = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

app = FastAPI(title="PetStore Agent Proxy")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    prompt: str


@app.get("/api/health")
def health():
    return {"status": "ok", "runtime_arn": RUNTIME_ARN or "(not set)", "region": REGION}


@app.post("/api/chat")
def chat(req: ChatRequest):
    if not RUNTIME_ARN:
        raise HTTPException(status_code=500, detail="RUNTIME_ARN is not configured")

    try:
        client = boto3.client("bedrock-agentcore", region_name=REGION)
        resp = client.invoke_agent_runtime(
            agentRuntimeArn=RUNTIME_ARN,
            qualifier="DEFAULT",
            contentType="application/json",
            payload=json.dumps({"prompt": req.prompt}).encode(),
        )

        raw = resp.get("response", b"")
        if hasattr(raw, "read"):
            raw = raw.read()
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode()

        # Strip Nova Pro inline reasoning tokens
        raw = re.sub(r"<thinking>.*?</thinking>", "", raw, flags=re.DOTALL).strip()

        # Response may be double-encoded (JSON string containing JSON string)
        data = json.loads(raw)
        if isinstance(data, str):
            data = json.loads(data)

        return data

    except json.JSONDecodeError as exc:
        log.error("JSON decode error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Could not parse agent response: {exc}")
    except Exception as exc:
        log.error("invoke_agent_runtime failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)
