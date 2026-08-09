"""OpenTelemetry distributed tracing integration.

This module provides optional OpenTelemetry tracing support. When the
opentelemetry packages are installed and OTEL_ENABLED=true, all HTTP
requests and key business operations will be traced.

If OpenTelemetry packages are not installed, all operations degrade
gracefully to no-ops.
"""

from __future__ import annotations

import os
from typing import Any, Callable

from loguru import logger

# Check if OpenTelemetry is available
_OTEL_AVAILABLE = False
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    _OTEL_AVAILABLE = True
except ImportError:
    pass


def is_enabled() -> bool:
    """Check if OpenTelemetry tracing is enabled via environment variable."""
    return _OTEL_AVAILABLE and os.environ.get("OTEL_ENABLED", "false").lower() in ("true", "1", "yes")


def setup_tracing(app=None) -> bool:
    """
    Initialize OpenTelemetry tracing with the configured exporter.

    Supports:
    - OTEL_EXPORTER=otlp (default) - OTLP exporter (Jaeger/Tempo/etc.)
    - OTEL_EXPORTER=console - Console exporter (for debugging)
    - OTEL_EXPORTER=none - No exporter (tracing API available but no export)

    Environment variables:
    - OTEL_ENABLED: Enable/disable tracing (default: false)
    - OTEL_EXPORTER: Exporter type (default: otlp)
    - OTEL_SERVICE_NAME: Service name (default: pygbsentry)
    - OTEL_EXPORTER_OTLP_ENDPOINT: OTLP endpoint (default: http://localhost:4317)
    - OTEL_EXPORTER_OTLP_PROTOCOL: OTLP protocol: grpc or http/protobuf (default: grpc)

    Returns:
        True if tracing was successfully set up, False otherwise.
    """
    if not _OTEL_AVAILABLE:
        logger.info("OpenTelemetry packages not installed, tracing disabled")
        return False

    if not is_enabled():
        logger.info("OpenTelemetry tracing disabled (OTEL_ENABLED not set)")
        return False

    try:
        service_name = os.environ.get("OTEL_SERVICE_NAME", "pygbsentry")
        resource = Resource.create({SERVICE_NAME: service_name})

        provider = TracerProvider(resource=resource)

        exporter_type = os.environ.get("OTEL_EXPORTER", "otlp").lower()

        if exporter_type == "console":
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter
            processor = BatchSpanProcessor(ConsoleSpanExporter())
            provider.add_span_processor(processor)
            logger.info(f"OpenTelemetry tracing enabled: console exporter, service={service_name}")

        elif exporter_type == "otlp":
            protocol = os.environ.get("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc").lower()
            endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

            if protocol == "http/protobuf":
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
                exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
            else:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
                exporter = OTLPSpanExporter(endpoint=endpoint)

            processor = BatchSpanProcessor(exporter)
            provider.add_span_processor(processor)
            logger.info(f"OpenTelemetry tracing enabled: OTLP/{protocol} exporter, endpoint={endpoint}, service={service_name}")

        elif exporter_type == "none":
            # No exporter, but tracing API is available
            logger.info(f"OpenTelemetry tracing enabled: no exporter, service={service_name}")

        else:
            logger.warning(f"Unknown OTEL_EXPORTER: {exporter_type}, tracing disabled")
            return False

        trace.set_tracer_provider(provider)

        # Auto-instrument FastAPI if app is provided
        if app is not None:
            try:
                FastAPIInstrumentor.instrument_app(app)
                logger.info("OpenTelemetry: FastAPI instrumented")
            except Exception as e:
                logger.warning(f"OpenTelemetry: FastAPI instrumentation failed: {e}")

        # Auto-instrument httpx
        try:
            HTTPXClientInstrumentor().instrument()
        except Exception as _inst_err:
            # FIX [2026-07-17 P3-25]: 描述性日志替代静默吞异常
            logger.debug(f"OpenTelemetry: httpx instrumentation failed: {_inst_err}")

        # Auto-instrument Redis
        try:
            RedisInstrumentor().instrument()
        except Exception as _inst_err:
            # FIX [2026-07-17 P3-25]: 描述性日志替代静默吞异常
            logger.debug(f"OpenTelemetry: Redis instrumentation failed: {_inst_err}")

        # Auto-instrument SQLAlchemy
        try:
            SQLAlchemyInstrumentor().instrument()
        except Exception as _inst_err:
            # FIX [2026-07-17 P3-25]: 描述性日志替代静默吞异常
            logger.debug(f"OpenTelemetry: SQLAlchemy instrumentation failed: {_inst_err}")

        return True

    except Exception as e:
        logger.warning(f"OpenTelemetry setup failed: {e}")
        return False


def get_tracer(name: str = "pygbsentry"):
    """Get a tracer instance. Returns a no-op tracer if OTEL is not available."""
    if _OTEL_AVAILABLE and is_enabled():
        return trace.get_tracer(name)
    return _NoOpTracer()


class _NoOpSpan:
    """No-op span that discards all operations."""
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def set_attribute(self, *args, **kwargs):
        pass
    def add_event(self, *args, **kwargs):
        pass
    def record_exception(self, *args, **kwargs):
        pass
    def set_status(self, *args, **kwargs):
        pass


class _NoOpTracer:
    """No-op tracer that returns no-op spans."""
    def start_as_current_span(self, *args, **kwargs):
        return _NoOpSpan()
    def start_span(self, *args, **kwargs):
        return _NoOpSpan()
