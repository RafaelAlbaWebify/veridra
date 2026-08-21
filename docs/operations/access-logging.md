# Production access logging

Veridra owns its HTTP access-log contract instead of relying on Uvicorn's default request-target logger.

## Log event

Each HTTP request emits one compact JSON event through the `veridra.access` logger:

```json
{"duration_ms":18,"event":"http_request","method":"GET","request_id":"4a9f...","route":"/projects/{project_id}","status":200,"timestamp":"2026-08-21T08:00:00+00:00"}
```

The event intentionally contains only:

- UTC timestamp;
- generated 24-hex-character request ID;
- HTTP method;
- matched route template, not the concrete request path;
- response status;
- bounded non-negative duration in milliseconds.

The same generated request ID is returned as `X-Request-ID` on normal application responses so customer-visible failures can be correlated with the protected server log without exposing session or tenant identity.

## Privacy boundary

The application access logger never records:

- query strings;
- concrete path parameters such as tenant/project IDs;
- request or response bodies;
- cookies;
- `Authorization` or other request headers;
- client-supplied request IDs;
- client IP addresses;
- authenticated user or tenant identity;
- password-reset/invitation tokens;
- Stripe webhook bodies or signatures.

Unmatched URLs are recorded as `<unmatched>` rather than echoing attacker-controlled path text.

This is important for `/reset-password` and `/accept-invitation`, where one-time tokens can appear in the browser query string before being posted back.

## Uvicorn and reverse-proxy logging

`veridra-api` disables Uvicorn's built-in access logger because the default request-target format may include a query string and would bypass the application redaction contract.

A reverse proxy, load balancer, CDN or hosting platform can still create its own request logs before traffic reaches Veridra. Configure every upstream layer to omit or redact query strings for sensitive routes, especially:

- `/reset-password`;
- `/accept-invitation`;
- any future route carrying one-time credentials in a query parameter.

Do not treat Veridra's application logger as proof that upstream access logs are safe.

## Operations

Capture the `veridra.access` stream in the same protected log sink as the web process. Recommended operational uses are:

- correlate a user-reported error with `X-Request-ID`;
- aggregate response status by route template;
- inspect latency by route template;
- detect bursts of `404`, `429`, `5xx`, or readiness failures.

Do not enrich access events downstream with raw request URLs, query strings, cookies or personal identifiers merely for convenience. Keep retention and log access bounded to operational need.
