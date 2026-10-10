from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from .config import settings


def configure_tracing():
    provider = TracerProvider(resource=Resource.create({"service.name": "enterprise-knowledge-api"}))
    if settings.otlp_endpoint:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otlp_endpoint)))
    trace.set_tracer_provider(provider)
    return trace.get_tracer("enterprise-knowledge-api")


tracer = configure_tracing()
