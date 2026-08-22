# Production response security headers

The composed Veridra runtime applies a global response-hardening middleware.

All HTTP responses receive:

- `X-Content-Type-Options: nosniff`;
- `Referrer-Policy: strict-origin-when-cross-origin` unless a route already supplied a stricter policy;
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`;
- a Content Security Policy with `default-src 'none'`, `script-src 'none'`, same-origin connection/form/font boundaries, `frame-src 'none'`, plugin/object blocking and constrained document base URLs;
- `style-src 'self' 'unsafe-inline'` while the existing server-rendered inline CSS remains in use;
- `img-src 'self' data:` so local assets and validated embedded PNG/JPEG report logos continue to render.

Non-embed routes also receive:

- `X-Frame-Options: DENY`;
- `Content-Security-Policy` with `frame-ancestors 'none'`.

Routes under `/embed/` intentionally omit anti-framing directives because those responses are designed to be embedded by customer sites. They remain unable to frame child content themselves and still receive the other global source restrictions.

Production responses additionally receive:

- `Strict-Transport-Security: max-age=31536000; includeSubDomains`.

HSTS assumes the documented production contract: the public origin and relevant subdomains are HTTPS. Do not expose a production Veridra hostname over plaintext HTTP after enabling this contract.

The middleware uses add-if-missing behavior. Route-specific responses such as password reset pages may retain stronger headers such as `Referrer-Policy: no-referrer`.

The current CSP deliberately blocks scripts entirely because the composed customer workflow is server-rendered and does not require client-side JavaScript. Inline CSS is the remaining relaxed directive. A future nonce/hash or static-stylesheet migration can remove `'unsafe-inline'` from `style-src`; that migration is not required to establish the current script, connection, framing and resource-source boundaries.
