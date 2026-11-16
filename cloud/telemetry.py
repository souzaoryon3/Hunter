"""Application Insights via OpenTelemetry; inativo sem connection string."""
import logging
import os

_configured = False


def quiet_sdk_logs():
    """O SDK registra cada requisicao HTTP em INFO; mantem apenas avisos."""
    for name in ("azure", "azure.core.pipeline.policies.http_logging_policy",
                 "azure.monitor.opentelemetry.exporter", "opentelemetry"):
        logging.getLogger(name).setLevel(logging.WARNING)


def enabled():
    return bool(os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING", "").strip())


def configure(service_name):
    """Envia traces, logs 'hunter.*' e metricas ao Azure Monitor. Retorna se ativou."""
    global _configured
    if _configured:
        return True
    if not enabled():
        return False
    os.environ.setdefault("OTEL_SERVICE_NAME", service_name)
    from azure.monitor.opentelemetry import configure_azure_monitor
    configure_azure_monitor(
        logger_name="hunter",
        enable_live_metrics=True,
        # Volume baixo: 100% dos traces (o padrao limita por segundo e perde rajadas).
        sampling_ratio=1.0,
        # FastAPI e instrumentado explicitamente por instrument_fastapi.
        instrumentation_options={"fastapi": {"enabled": False}},
    )
    logging.getLogger("hunter").setLevel(logging.INFO)
    _configured = True
    return True


def instrument_fastapi(app):
    if not configure("hunter-api"):
        return False
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    # Healthchecks do Docker rodam a cada 5 s; fora da telemetria para economizar.
    FastAPIInstrumentor.instrument_app(app, excluded_urls="health/live,health/ready")
    return True


def meter():
    from opentelemetry import metrics
    return metrics.get_meter("hunter.azure")


def flush():
    """Garante o envio antes de processos curtos (CLI/backup) terminarem."""
    if not _configured:
        return
    from opentelemetry import _logs, metrics, trace
    for provider in (trace.get_tracer_provider(), _logs.get_logger_provider(),
                     metrics.get_meter_provider()):
        force = getattr(provider, "force_flush", None)
        if force:
            force()
