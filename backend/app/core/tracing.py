from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource

def setup_tracing(service_name: str = "portalis-rag"):
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    try:
        exporter = OTLPSpanExporter()
        processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(processor)
    except Exception:
        pass
    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)

tracer = setup_tracing()
