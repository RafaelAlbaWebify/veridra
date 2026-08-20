# Production response security headers

The composed Veridra runtime applies a global response-hardening middleware.

All HTTP responses receive:

- `X-Content-Type-Options: nosniff`;
- `Referrer-Policy: strict-origin-when-cross-origin` unless a route already supplied a stricter policy;
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`;
- a narrow Content Security Policy that blocks plugin/object content and constrains document base URLs.

Non-embed routes also receive:

- `X-Frame-Options: DENY`;
- `Content-Security-Policy` with `frame-ancestors 'none'`.

Routes under `/embed/` intentionally omit anti-framing directives because those responses are designed to be embedded by customer sites. They still receive the other global hardening headers.

Production responses additionally receive:

- `Strict-Transport-Security: max-age=31536000; includeSubDomains`.

HSTS assumes the documented production contract: the public origin and relevant subdomains are HTTPS. Do not expose a production Veridra hostname over plaintext HTTP after enabling this contract.

The middleware uses add-if-missing behavior. Route-specific responses such as password reset pages may retain stronger headers such as `Referrer-Policy: no-referrer`.

The CSP is intentionally narrow rather than declaring `default-src 'self'` today. Veridra currently renders inline styles in several server-generated pages; adopting a stricter script/style policy requires a separate nonce/hash migration and browser validation rather than silently breaking UI in a security-header change.
