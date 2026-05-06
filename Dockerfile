FROM --platform=linux/arm64 public.ecr.aws/docker/library/python:3.12-slim-bookworm

WORKDIR /app

# Copy requirements first so Docker layer cache avoids re-running pip
# when only .py files change.
COPY pet_store_agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir bedrock-agentcore
RUN pip install --no-cache-dir aws-opentelemetry-distro

COPY pet_store_agent/*.py ./

# Runtime config injected by AgentCore (KB IDs, Lambda names) is passed
# as environment variables at deploy time — not baked into the image.
ENV AWS_DEFAULT_REGION=us-east-1
ENV OTEL_PYTHON_DISTRO=aws_distro
ENV OTEL_PYTHON_CONFIGURATOR=aws_configurator
ENV OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
ENV OTEL_TRACES_EXPORTER=otlp
ENV OTEL_RESOURCE_ATTRIBUTES=service.name=petstore-agent
ENV AGENT_OBSERVABILITY_ENABLED=true

EXPOSE 8080
CMD ["opentelemetry-instrument", "python", "agentcore_entrypoint.py"]
