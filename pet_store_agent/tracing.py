# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#
# Arize AX tracing — OpenInference instrumentation for LangChain/LangGraph.
#
# Traces every LLM call, tool invocation, and ReAct reasoning step and sends
# them to Arize AX (app.arize.com) via OTLP/HTTP.
#
# Environment variables (required):
#   ARIZE_SPACE_ID       Your Arize Space ID
#   ARIZE_API_KEY        Your Arize API key
#
# Optional:
#   ARIZE_PROJECT_NAME   Project name in Arize UI  (default: virtual-pet-store-agent)

import logging
import os

logger = logging.getLogger(__name__)
_tracing_initialised = False


def setup_tracing() -> None:
    """
    Create a dedicated Arize TracerProvider and instrument LangChain with it.

    Arize requires arize.project.name as a *span* attribute (not resource attribute).
    We attach it automatically via a SpanProcessor so every span is routed correctly.
    """
    global _tracing_initialised
    if _tracing_initialised:
        return
    _tracing_initialised = True

    try:
        from openinference.instrumentation.langchain import LangChainInstrumentor
        from opentelemetry.sdk.trace import TracerProvider, SpanProcessor
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    except ImportError as e:
        logger.warning("Tracing packages not installed — skipping. (%s)", e)
        return

    space_id     = os.environ.get("ARIZE_SPACE_ID", "")
    api_key      = os.environ.get("ARIZE_API_KEY", "")
    project_name = os.environ.get("ARIZE_PROJECT_NAME", "virtual-pet-store-agent")

    if not space_id or not api_key:
        logger.warning("ARIZE_SPACE_ID or ARIZE_API_KEY not set — tracing disabled.")
        return

    class _ArizeProjectProcessor(SpanProcessor):
        """Stamps every span with arize.project.name so Arize routes it correctly."""
        def on_start(self, span, parent_context=None):
            span.set_attribute("arize.project.name", project_name)
        def on_end(self, span): pass
        def shutdown(self): pass
        def force_flush(self, timeout_millis=30000): return True

    # AgentCore sets OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://xray.us-east-1.amazonaws.com/v1/traces
    # which overrides our explicit endpoint, routing spans to X-Ray instead of Arize.
    # We must unset it before constructing OTLPSpanExporter.
    os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
    os.environ.pop("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", None)

    arize_exporter = OTLPSpanExporter(
        endpoint="https://otlp.arize.com/v1/traces",
        headers={
            "authorization": f"Bearer {api_key}",
            "space_id": space_id,
        },
    )

    arize_provider = TracerProvider()
    arize_provider.add_span_processor(_ArizeProjectProcessor())
    arize_provider.add_span_processor(BatchSpanProcessor(arize_exporter))

    # AgentCore auto-instruments LangChain before our code runs.
    # Uninstrument first so our re-instrument with arize_provider is not ignored.
    instrumentor = LangChainInstrumentor()
    if instrumentor.is_instrumented_by_opentelemetry:
        instrumentor.uninstrument()
    instrumentor.instrument(tracer_provider=arize_provider)
    logger.info("Arize AX tracing enabled (project: %s)", project_name)
