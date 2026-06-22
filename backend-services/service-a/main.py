from fastapi import FastAPI, Request
from prometheus_fastapi_instrumentator import Instrumentator
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
import hashlib
import os

# OTel setup
OTEL_ENDPOINT = os.getenv("OTEL_ENDPOINT", "")

provider = TracerProvider()
if OTEL_ENDPOINT:
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=OTEL_ENDPOINT, insecure=True)
        )
    )
trace.set_tracer_provider(provider)

# App
app = FastAPI(title="Service A", description="CPU-bound service")
FastAPIInstrumentor.instrument_app(app)

Instrumentator(
    should_group_status_codes=False,
    should_group_untemplated=False,
).instrument(app).expose(app, endpoint="/metrics")

tracer = trace.get_tracer("service-a")

# Routes
@app.get("/api/cpu")
def cpu_endpoint(request: Request):
    client_id = request.headers.get("X-Client-ID", "unknown")
    with tracer.start_as_current_span("cpu-work") as span:
        span.set_attribute("client.id", client_id)
        result = hashlib.sha256(b"x" * 100_000).hexdigest()
    return {
        "service":   "A",
        "endpoint":  "cpu",
        "client_id": client_id,
        "result":    result[:16],
    }

@app.get("/api/light")
def light_endpoint(request: Request):
    client_id = request.headers.get("X-Client-ID", "unknown")
    return {
        "service":   "A",
        "endpoint":  "light",
        "client_id": client_id,
        "result":    "ok",
    }

@app.get("/health")
def health():
    return {"status": "ok", "service": "A"}

@app.get("/")
def root():
    return {"service": "A", "status": "running"}
