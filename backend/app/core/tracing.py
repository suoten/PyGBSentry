"""Distributed tracing setup (best-effort, optional).

When OpenTelemetry is installed and configured via environment variables, this
wires FastAPI/SQLAlchemy instrumentation. When OTel is unavailable, it is a
no-op so tracing never blocks startup.
"""
from __future__ import annotations

from typing import Any

from loguru import logger


def setup_tracing(app: Any = None, **kwargs: Any) -> bool:
    """Initialise OpenTelemetry tracing if available.

    Returns True when tracing was enabled, False otherwise. Failures are
    logged at DEBUG level and swallowed.

    FIX: [2026-07-10] 原实现只要 opentelemetry 包安装就强制启用 tracing，
    但 main.py 注释声称 "enabled via OTEL_ENABLED=true"。
    实际未检查 OTEL_ENABLED 导致 tracing 总是开启。
    更严重的是 FastAPIInstrumentor 的 ASGI 中间件在遇到未匹配路由时
    尝试访问 scope["route"].path，但 scope["route"] 是 _IncludedRouter
    对象（无 .path 属性），导致 500 错误。
    修复：严格按 OTEL_ENABLED=true 才启用，默认关闭。 [全栈工程师]
    """
    import os
    # FIX: [2026-07-10] tracing 必须显式 opt-in，避免 OpenTelemetry ASGI 中间件
    # 在未匹配路由时崩溃（_IncludedRouter 无 .path 属性导致 500）
    if os.environ.get("OTEL_ENABLED", "false").lower() != "true":
        logger.debug("tracing: OTEL_ENABLED!=true, tracing disabled (opt-in)")
        return False
    service_name = os.environ.get("OTEL_SERVICE_NAME") or "PyGBSentry"
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        # Console exporter is optional; only add if explicitly requested.
        exporter_kind = os.environ.get("OTEL_EXPORTER", "").lower()
        if exporter_kind in ("otlp", "otlp_proto_grpc", "otlp_proto_http"):
            try:
                if "grpc" in exporter_kind:
                    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
                else:
                    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
                provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
            except Exception as e:
                logger.debug(f"tracing: OTLP exporter unavailable: {e}")

        trace.set_tracer_provider(provider)

        if app is not None:
            try:
                from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
                FastAPIInstrumentor.instrument_app(app)
            except Exception as e:
                logger.debug(f"tracing: FastAPI instrumentation skipped: {e}")
            try:
                from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
                SQLAlchemyInstrumentor.instrument()
            except Exception as e:
                logger.debug(f"tracing: SQLAlchemy instrumentation skipped: {e}")

        logger.info(f"tracing: enabled (service={service_name})")
        return True
    except ImportError:
        logger.debug("tracing: opentelemetry not installed; tracing disabled")
        return False
    except Exception as e:
        logger.debug(f"tracing: setup failed: {e}")
        return False
