import httpx
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse
from prometheus_client import Counter, Histogram
from prometheus_fastapi_instrumentator import Instrumentator
from .config import settings
from .rate_limiter import TokenBucketLimiter
from .redis_client import LabelReader


app = FastAPI(title="Balancit Proxy", description="ML-driven contextual load balancer")

# Per-client custom metrics
proxy_requests_total = Counter(
    "proxy_requests_total",
    "Total requests through the proxy, labeled by client_id, service, and status",
    ["client_id", "service", "status"],
)
proxy_request_duration_seconds = Histogram(
    "proxy_request_duration_seconds",
    "Request duration through the proxy, labeled by client_id and service",
    ["client_id", "service"],
)
proxy_throttled_total = Counter(
    "proxy_throttled_total",
    "Requests rejected by rate limiter, labeled by client_id, service, mode, and reason",
    ["client_id", "service", "mode", "reason"],
)
proxy_label_lookups_total = Counter(
    "proxy_label_lookups_total",
    "Redis label lookups, labeled by client_id and resolved_label",
    ["client_id", "resolved_label"],
)

Instrumentator(
    should_group_status_codes=False,
    should_group_untemplated=False,
).instrument(app).expose(app, endpoint="/metrics")

http_client: httpx.AsyncClient | None = None
static_limiter: TokenBucketLimiter | None = None
genuine_limiter: TokenBucketLimiter | None = None
suspicious_limiter: TokenBucketLimiter | None = None
untrusted_limiter: TokenBucketLimiter | None = None
label_reader: LabelReader | None = None


@app.on_event("startup")
async def startup():
    global http_client, static_limiter
    global genuine_limiter, suspicious_limiter, untrusted_limiter
    global label_reader

    http_client = httpx.AsyncClient(timeout=settings.upstream_timeout)
    static_limiter = TokenBucketLimiter(
        rate_per_second=settings.static_rate_per_second,
        capacity=settings.static_bucket_capacity,
    )
    genuine_limiter = TokenBucketLimiter(
        rate_per_second=settings.rate_genuine_rps,
        capacity=settings.rate_genuine_capacity,
    )
    suspicious_limiter = TokenBucketLimiter(
        rate_per_second=settings.rate_suspicious_rps,
        capacity=settings.rate_suspicious_capacity,
    )
    untrusted_limiter = TokenBucketLimiter(
        rate_per_second=settings.rate_untrusted_rps,
        capacity=settings.rate_untrusted_capacity,
    )
    label_reader = LabelReader()

    print(f"[proxy] Started on :{settings.proxy_port} in mode={settings.proxy_mode}", flush=True)


@app.on_event("shutdown")
async def shutdown():
    if http_client:
        await http_client.aclose()


@app.get("/health")
def health():
    return {"status": "ok", "service": "proxy", "mode": settings.proxy_mode}


@app.get("/")
def root():
    return {"service": "balancit-proxy", "status": "running", "mode": settings.proxy_mode}


def _resolve_upstream(service: str) -> str:
    if service == "service-a":
        return settings.service_a_url
    if service == "service-b":
        return settings.service_b_url
    raise HTTPException(status_code=404, detail=f"Unknown service: {service}")


def _resolve_label(client_id: str) -> str:
    """Map Redis label to a tier the proxy understands. Fail-open to UNTRUSTED."""
    raw = label_reader.get_label(client_id)
    if raw is None:
        return "UNTRUSTED"
    if raw == "GENUINE":
        return "GENUINE"
    if raw == "SUSPICIOUS":
        return "SUSPICIOUS"
    if raw == "ANOMALY":
        return "ANOMALY"
    # WARMUP, IDLE, or unknown values all treated as UNTRUSTED
    return "UNTRUSTED"


async def _admission_check(client_id: str, service: str) -> tuple[bool, str | None]:
    """Returns (allowed, reason_if_blocked)."""
    if settings.proxy_mode == "none":
        return True, None

    if settings.proxy_mode == "static":
        allowed = await static_limiter.allow(client_id)
        return allowed, None if allowed else "static_rate_limit"

    if settings.proxy_mode == "ml":
        label = _resolve_label(client_id)
        proxy_label_lookups_total.labels(
            client_id=client_id, resolved_label=label
        ).inc()

        if label == "ANOMALY":
            return False, "anomaly_blocked"

        if label == "GENUINE":
            allowed = await genuine_limiter.allow(client_id)
            return allowed, None if allowed else "genuine_rate_limit"

        if label == "SUSPICIOUS":
            allowed = await suspicious_limiter.allow(client_id)
            return allowed, None if allowed else "suspicious_rate_limit"

        # UNTRUSTED (covers WARMUP, IDLE, missing, unknown)
        allowed = await untrusted_limiter.allow(client_id)
        return allowed, None if allowed else "untrusted_rate_limit"

    return True, None


@app.api_route(
    "/{service}/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def proxy(service: str, path: str, request: Request):
    client_id = request.headers.get("X-Client-ID", "unknown")
    upstream_base = _resolve_upstream(service)
    upstream_url = f"{upstream_base}/{path}"

    allowed, reason = await _admission_check(client_id, service)
    if not allowed:
        proxy_throttled_total.labels(
            client_id=client_id, service=service, mode=settings.proxy_mode,
            reason=reason or "unknown",
        ).inc()
        proxy_requests_total.labels(
            client_id=client_id, service=service, status="429"
        ).inc()
        return JSONResponse(
            status_code=429,
            content={"error": "rate_limited", "reason": reason},
        )

    headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}

    with proxy_request_duration_seconds.labels(
        client_id=client_id, service=service
    ).time():
        try:
            body = await request.body()
            upstream_response = await http_client.request(
                method=request.method,
                url=upstream_url,
                headers=headers,
                content=body,
                params=request.query_params,
            )
            status = upstream_response.status_code
        except httpx.RequestError as e:
            proxy_requests_total.labels(
                client_id=client_id, service=service, status="502"
            ).inc()
            return PlainTextResponse(f"Upstream error: {e}", status_code=502)

    proxy_requests_total.labels(
        client_id=client_id, service=service, status=str(status)
    ).inc()

    drop_headers = {"content-encoding", "transfer-encoding", "connection"}
    response_headers = {
        k: v for k, v in upstream_response.headers.items()
        if k.lower() not in drop_headers
    }

    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=response_headers,
    )
