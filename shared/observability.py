"""Observability — structured logging, Prometheus metrics, and tracing.

Usage:
    from shared.observability import setup_logging, setup_metrics, setup_tracing
    setup_logging()
    setup_metrics(app)
    setup_tracing(app, service_name="hermes-engine")
"""

from __future__ import annotations

import logging
import sys


# ── Structured logging ──────────────────────────────────────────────────

def setup_logging(level: int = logging.INFO) -> None:
    """Configure structured JSON logging via python-json-logger if available.

    Falls back to plain-text logging when the package is not installed.
    """
    try:
        from pythonjsonlogger import jsonlogger
    except ImportError:
        # Fallback: keep the default plain-text format
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
            stream=sys.stdout,
        )
        return

    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)
    logging.basicConfig(level=level, handlers=[handler])
    logging.getLogger("uvicorn.access").handlers = [handler]


# ── Prometheus metrics ──────────────────────────────────────────────────

def setup_metrics(app) -> None:
    """Attach Prometheus metrics instrumentation to the FastAPI app.

    Exposes ``GET /metrics`` for scraping.
    """
    try:
        from prometheus_fastapi_instrumentator import Instrumentator
        Instrumentator().instrument(app).expose(app)
    except ImportError:
        pass


# ── OpenTelemetry tracing ───────────────────────────────────────────────

def setup_tracing(app, service_name: str = "hermes-engine") -> None:
    """Configure OpenTelemetry auto-instrumentation for FastAPI.

    Traces are exported to the console by default.  Set
    ``OTEL_EXPORTER_OTLP_ENDPOINT`` to send to a collector.
    """
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource(attributes={SERVICE_NAME: service_name})
        provider = TracerProvider(resource=resource)
        processor = BatchSpanProcessor(OTLPSpanExporter())
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)

        FastAPIInstrumentor.instrument_app(app)
    except ImportError:
        pass
