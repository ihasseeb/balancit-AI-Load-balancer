from fastapi import FastAPI, Request
from prometheus_fastapi_instrumentator import Instrumentator
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
import asyncio
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
app = FastAPI(title="Service B", description="I/O-bound service")
FastAPIInstrumentor.instrument_app(app)

Instrumentator(
    should_group_status_codes=False,
    should_group_untemplated=False,
).instrument(app).expose(app, endpoint="/metrics")

tracer = trace.get_tracer("service-b")

# Routes
@app.get("/api/io")
async def io_endpoint(request: Request):
    """Simulates a database query or network call (~150ms)."""
    client_id = request.headers.get("X-Client-ID", "unknown")
    with tracer.start_as_current_span("io-work") as span:
        span.set_attribute("client.id", client_id)
        await asyncio.sleep(0.15)
    return {
        "service":   "B",
        "endpoint":  "io",
        "client_id": client_id,
        "result":    "done",
    }

@app.get("/api/slow")
async def slow_endpoint(request: Request):
    """Simulates an expensive I/O operation (~500ms)."""
    client_id = request.headers.get("X-Client-ID", "unknown")
    with tracer.start_as_current_span("slow-work") as span:
        span.set_attribute("client.id", client_id)
        await asyncio.sleep(0.5)
    return {
        "service":   "B",
        "endpoint":  "slow",
        "client_id": client_id,
        "result":    "slow_done",
    }

@app.get("/health")
def health():
    return {"status": "ok", "service": "B"}

@app.get("/")
def root():
    return {"service": "B", "status": "running"}
